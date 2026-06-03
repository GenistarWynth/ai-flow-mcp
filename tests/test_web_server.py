from __future__ import annotations

import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts.ai_flow.artifacts import write_text
from scripts.ai_flow.state import PLANNED, REVIEWED_PASS, create_status, set_status


class WebServerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.run_id = "run-web"
        self.run_dir = self.tmp / ".ai" / "runs" / self.run_id
        self.run_dir.mkdir(parents=True)
        create_status(
            self.run_dir,
            run_id=self.run_id,
            task="web task",
            repo_root=self.tmp,
            config_path=self.tmp / ".ai" / "patchbay.toml",
        )
        set_status(self.run_dir, PLANNED)
        write_text(self.run_dir / "events.jsonl", '{"phase":"plan","action":"success"}\n')
        write_text(self.run_dir / "FINAL.diff", "diff --git a/a.txt b/a.txt\n")
        write_text(self.run_dir / "writer.log", "line 1\nline 2\nline 3\n")

    def tearDown(self) -> None:
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def _server(self):
        from scripts.ai_flow.web_server import create_server

        server = create_server(self.tmp, host="127.0.0.1", port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 2)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server

    def _request(self, method: str, path: str, payload: dict[str, object] | None = None):
        server = self._server()
        host, port = server.server_address
        data = None
        headers = {}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            f"http://{host}:{port}{path}",
            data=data,
            method=method,
            headers=headers,
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            body = response.read().decode("utf-8")
            return response.status, json.loads(body)

    def test_health_runs_status_events_trace_artifact_and_diff_endpoints(self) -> None:
        status, health = self._request("GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(health["status"], "ok")

        _, runs = self._request("GET", "/api/runs")
        self.assertEqual(runs["count"], 1)
        self.assertEqual(runs["runs"][0]["run_id"], self.run_id)

        _, run_status = self._request("GET", f"/api/runs/{self.run_id}/status")
        self.assertEqual(run_status["run_id"], self.run_id)
        self.assertFalse(run_status["gate_state"]["ready_to_apply"])

        _, context = self._request("GET", f"/api/runs/{self.run_id}/context")
        self.assertEqual(context["run_id"], self.run_id)
        self.assertEqual(context["timeline"][0]["source"], "event")
        self.assertIn("next_actions", context)
        self.assertIn("agent_activity", context)
        self.assertIn("headline", context["agent_activity"])
        self.assertIn("messages", context["agent_activity"])
        self.assertIn("conversation_state", context["agent_activity"])

        _, events = self._request("GET", f"/api/runs/{self.run_id}/events")
        self.assertEqual(events["returned"], 1)

        _, trace = self._request("GET", f"/api/runs/{self.run_id}/trace")
        self.assertEqual(trace["run_id"], self.run_id)
        self.assertIn("trace", trace)

        _, artifact = self._request("GET", f"/api/runs/{self.run_id}/artifact/writer.log?tail=2")
        self.assertEqual(artifact["text"], "line 2\nline 3\n")

        _, diff = self._request("GET", f"/api/runs/{self.run_id}/diff")
        self.assertEqual(diff["text"], "diff --git a/a.txt b/a.txt\n")

    def test_post_action_calls_existing_service_function(self) -> None:
        from scripts.ai_flow import web_server

        with patch.object(web_server.service, "approve", return_value={"status": "APPROVED"}) as approve:
            status, result = self._request("POST", f"/api/runs/{self.run_id}/actions/approve")

        self.assertEqual(status, 200)
        self.assertEqual(result["status"], "APPROVED")
        approve.assert_called_once_with(self.tmp, self.run_id)

    def test_post_runs_creates_plan_run(self) -> None:
        from scripts.ai_flow import web_server

        with patch.object(
            web_server.service,
            "plan_with_context",
            return_value={
                "run_id": "run-new",
                "status": "PLANNED",
                "routing": {"economy_configured": True},
                "actions": [{"id": "show_runs", "kind": "local_agent", "message": "status"}],
                "action_groups": [{"id": "local", "action_ids": ["show_runs"]}],
            },
        ) as plan:
            status, result = self._request("POST", "/api/runs", {"task": "new task"})

        self.assertEqual(status, 200)
        self.assertEqual(result["run_id"], "run-new")
        self.assertTrue(result["routing"]["economy_configured"])
        self.assertEqual(result["actions"][0]["id"], "show_runs")
        self.assertEqual(result["action_groups"][0]["id"], "local")
        plan.assert_called_once_with(self.tmp, task="new task")

    def test_post_runs_can_start_background_plan(self) -> None:
        from scripts.ai_flow import web_server

        with patch.object(web_server.service, "start_background_phase", return_value={"run_id": "run-bg", "background": True}) as start:
            status, result = self._request("POST", "/api/runs", {"task": "background task", "background": True})

        self.assertEqual(status, 200)
        self.assertEqual(result["run_id"], "run-bg")
        start.assert_called_once_with(self.tmp, "plan", task="background task")

    def test_agent_message_endpoint_forwards_background(self) -> None:
        from scripts.ai_flow import web_server

        with patch.object(web_server, "agent_message", return_value={"run_id": "run-bg", "background": True}) as agent:
            status, result = self._request(
                "POST",
                "/api/agent/message",
                {
                    "message": "continue",
                    "run_id": self.run_id,
                    "confirmation": "none",
                    "include": {"diff": True},
                    "max_fix_rounds": 1,
                    "background": True,
                },
            )

        self.assertEqual(status, 200)
        self.assertTrue(result["background"])
        agent.assert_called_once_with(
            self.tmp,
            "continue",
            run_id=self.run_id,
            confirmation="none",
            include={"diff": True},
            max_fix_rounds=1,
            background=True,
        )

    def test_apply_action_is_rejected_until_gate_ready(self) -> None:
        from scripts.ai_flow import web_server

        with (
            patch.object(
                web_server.service,
                "status",
                return_value={"gate_state": {"ready_to_apply": False}, "tests_passed": False, "review_result": None},
            ),
            patch.object(web_server.service, "apply", return_value={"status": "APPLIED"}) as apply,
        ):
            with self.assertRaises(urllib.error.HTTPError) as caught:
                self._request("POST", f"/api/runs/{self.run_id}/actions/apply")

        self.assertEqual(caught.exception.code, 409)
        apply.assert_not_called()

    def test_apply_action_runs_when_tests_and_review_passed(self) -> None:
        from scripts.ai_flow import web_server

        with (
            patch.object(
                web_server.service,
                "status",
                return_value={
                    "status": REVIEWED_PASS,
                    "tests_passed": True,
                    "review_result": "PASS",
                    "gate_state": {"ready_to_apply": True},
                },
            ),
            patch.object(web_server.service, "apply", return_value={"status": "APPLIED"}) as apply,
        ):
            status, result = self._request(
                "POST",
                f"/api/runs/{self.run_id}/actions/apply",
                {"confirmation": "apply_approved"},
            )

        self.assertEqual(status, 200)
        self.assertEqual(result["status"], "APPLIED")
        apply.assert_called_once_with(self.tmp, self.run_id)

    def test_apply_action_requires_explicit_confirmation_when_gate_ready(self) -> None:
        from scripts.ai_flow import web_server

        with (
            patch.object(
                web_server.service,
                "status",
                return_value={
                    "status": REVIEWED_PASS,
                    "tests_passed": True,
                    "review_result": "PASS",
                    "gate_state": {"ready_to_apply": True},
                },
            ),
            patch.object(web_server.service, "apply", return_value={"status": "APPLIED"}) as apply,
        ):
            with self.assertRaises(urllib.error.HTTPError) as caught:
                self._request("POST", f"/api/runs/{self.run_id}/actions/apply")

        self.assertEqual(caught.exception.code, 409)
        apply.assert_not_called()

    def test_config_and_provider_endpoints_reuse_config_wizard_helpers(self) -> None:
        status, config = self._request("GET", "/api/config")
        self.assertEqual(status, 200)
        self.assertIn("resolved", config)

        status, doctor = self._request("GET", "/api/doctor")
        self.assertEqual(status, 200)
        self.assertIn("checks", doctor)
        self.assertTrue(doctor["checks"]["mcp"]["skipped"])
        self.assertIn("profile", doctor["checks"]["config"])
        self.assertIn("phase_strategy", doctor["checks"]["config"]["profile"])

        _, updated = self._request("PUT", "/api/config", {"key": "models.planner", "value": "mock-model"})
        self.assertEqual(updated["set"], {"models.planner": "mock-model"})

        _, profile = self._request("GET", "/api/config/profile")
        self.assertIn("economy", profile)
        self.assertIn("phase_strategy", profile)

        _, applied_profile = self._request("POST", "/api/config/profile/apply", {"profile": "economy"})
        self.assertEqual(applied_profile["profile"], "economy")
        self.assertTrue(applied_profile["status"]["economy"]["matches"])
        self.assertEqual(applied_profile["status"]["phase_strategy"]["write"]["model"], "deepseek-v4-pro")

        provider_payload = {
            "provider_id": "local_writer",
            "roles": ["write"],
            "command": "local-writer",
            "args": ["--json"],
            "prompt_mode": "stdin",
            "output_contract": "worktree_diff",
        }
        _, provider = self._request("POST", "/api/providers", provider_payload)
        self.assertEqual(provider["provider"], "local_writer")

        _, providers = self._request("GET", "/api/providers")
        self.assertIn("local_writer", providers["providers"])

    def test_provider_endpoint_can_activate_economy_route(self) -> None:
        payload = {
            "provider_id": "cheap_writer",
            "roles": ["write", "fix"],
            "command": "deepseek-writer",
            "args": ["--json"],
            "prompt_mode": "stdin",
            "output_contract": "writer_diff",
            "activate_economy": True,
            "economy_model": "deepseek-chat",
            "economy_label": "DeepSeek cheap writer",
        }

        status, provider = self._request("POST", "/api/providers", payload)

        self.assertEqual(status, 200)
        self.assertEqual(provider["provider"], "cheap_writer")
        self.assertTrue(provider["activated_economy"])
        self.assertEqual(provider["economy_updated"]["phases.write.provider"], "cheap_writer")
        self.assertEqual(provider["economy_updated"]["phases.fix.provider"], "cheap_writer")
        self.assertEqual(provider["status"]["phase_strategy"]["write"]["provider"], "cheap_writer")
        self.assertEqual(provider["status"]["phase_strategy"]["fix"]["model"], "deepseek-chat")
        self.assertIn("action_groups", provider)

    def test_doctor_endpoint_can_suppress_mcp_followup_actions(self) -> None:
        from scripts.ai_flow import web_server

        with patch.object(web_server, "run_doctor", return_value={"ok": True, "checks": {}}) as doctor:
            status, result = self._request("GET", "/api/doctor?include_mcp=true&skip_mcp=true&host=Claude%20Desktop")

        self.assertEqual(status, 200)
        self.assertTrue(result["ok"])
        doctor.assert_called_once_with(
            self.tmp,
            include_mcp=False,
            skill_path=None,
            host="Claude Desktop",
            suppress_mcp_actions=True,
        )

    def test_cli_parser_accepts_web_json_host_and_port(self) -> None:
        from scripts.ai_flow.cli import build_parser

        args = build_parser().parse_args(["web", "--host", "127.0.0.1", "--port", "0", "--json"])

        self.assertEqual(args.command, "web")
        self.assertEqual(args.host, "127.0.0.1")
        self.assertEqual(args.port, 0)
        self.assertTrue(args.json)


if __name__ == "__main__":
    unittest.main()
