from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

from scripts.ai_flow.agent import APPLY_CONFIRMATION, PLAN_CONFIRMATION, agent_message


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


class AgentTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = Path(tempfile.mkdtemp(prefix="patchbay-agent-"))
        self.repo = self.tempdir / "repo"
        self.repo.mkdir()
        self.script = PROJECT_ROOT / "scripts" / "patchbay"
        run(["git", "init"], self.repo)
        run(["git", "config", "user.email", "patchbay@example.test"], self.repo)
        run(["git", "config", "user.name", "Patchbay tests"], self.repo)
        (self.repo / "README.md").write_text("# Agent Repo\n", encoding="utf-8")
        (self.repo / ".gitignore").write_text(
            ".ai/runs/\n.ai/logs/\n.ai/worktrees/\n.ai/patchbay.toml\n.patchbay-worktrees/\n",
            encoding="utf-8",
        )
        run(["git", "add", "README.md", ".gitignore"], self.repo)
        run(["git", "commit", "-m", "initial"], self.repo)
        self._write_mock_config(allow_without_tests=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.tempdir, ignore_errors=True)

    def _write_mock_config(self, *, allow_without_tests: bool) -> None:
        path = self.repo / ".ai" / "patchbay.toml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f"""[phases.plan]
provider = "mock"

[phases.write]
provider = "mock"

[phases.review]
provider = "mock"

[phases.fix]
provider = "mock"

[workflow]
allow_apply_without_tests = {str(allow_without_tests).lower()}

[commands_allowlist]
test = []
""",
            encoding="utf-8",
        )

    def cli_json(self, *args: str) -> dict:
        completed = run(["python", str(self.script), *args, "--json"], self.repo)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return json.loads(completed.stdout)

    def wait_for(self, predicate, *, timeout: float = 8.0):
        deadline = time.time() + timeout
        last = None
        while time.time() < deadline:
            last = predicate()
            if last:
                return last
            time.sleep(0.1)
        self.fail(f"Timed out waiting for condition; last value: {last!r}")


class AgentWorkflowTests(AgentTestCase):
    def test_agent_new_message_returns_plan_and_gate(self) -> None:
        response = agent_message(self.repo, "agent plans first")

        self.assertTrue(response["ok"])
        self.assertEqual(response["status"]["status"], "PLANNED")
        self.assertEqual(response["requires_confirmation"]["confirmation"], PLAN_CONFIRMATION)
        self.assertIn("PLAN.md", response["artifacts"])
        self.assertIn("Mock Implementation Plan", response["artifacts"]["PLAN.md"]["text"])
        self.assertEqual(response["context"]["next_actions"][0]["name"], "approve")

    def test_agent_doctor_message_returns_readiness_without_starting_run(self) -> None:
        response = agent_message(self.repo, "doctor")

        self.assertEqual(response["action"], "doctor")
        self.assertIn("doctor", response)
        self.assertIn("checks", response["doctor"])
        self.assertIsNone(response["run_id"])
        self.assertFalse((self.repo / ".ai" / "runs").exists())

    def test_agent_doctor_word_in_task_still_starts_plan(self) -> None:
        response = agent_message(self.repo, "build doctor profile workflow")

        self.assertEqual(response["action"], "start")
        self.assertEqual(response["status"]["status"], "PLANNED")
        self.assertIsNotNone(response["run_id"])

        patchbay_task = agent_message(self.repo, "fix patchbay doctor bug")
        self.assertEqual(patchbay_task["action"], "start")
        self.assertEqual(patchbay_task["status"]["status"], "PLANNED")

    def test_agent_refuses_approval_without_confirmation(self) -> None:
        planned = agent_message(self.repo, "needs approval")
        run_id = planned["run_id"]

        response = agent_message(self.repo, "approve", run_id=run_id)

        self.assertEqual(response["status"]["status"], "PLANNED")
        self.assertEqual(response["requires_confirmation"]["confirmation"], PLAN_CONFIRMATION)
        self.assertFalse((self.repo / ".ai" / "runs" / run_id / "APPROVAL.json").exists())

    def test_agent_approve_and_run_reaches_apply_gate(self) -> None:
        planned = agent_message(self.repo, "ready for agent autopilot")

        response = agent_message(self.repo, "approve", run_id=planned["run_id"], confirmation=PLAN_CONFIRMATION)

        self.assertTrue(response["ok"])
        self.assertEqual(response["status"]["status"], "REVIEWED_PASS")
        self.assertTrue(response["status"]["gate_state"]["ready_to_apply"])
        self.assertEqual(response["requires_confirmation"]["confirmation"], APPLY_CONFIRMATION)
        self.assertIn("PATCHBAY_MOCK_OUTPUT.md", response["diff"])

    def test_agent_apply_requires_confirmation(self) -> None:
        planned = agent_message(self.repo, "apply confirmation")
        run_id = planned["run_id"]
        agent_message(self.repo, "approve", run_id=run_id, confirmation=PLAN_CONFIRMATION)

        refused = agent_message(self.repo, "apply", run_id=run_id)
        self.assertEqual(refused["requires_confirmation"]["confirmation"], APPLY_CONFIRMATION)
        self.assertFalse((self.repo / "PATCHBAY_MOCK_OUTPUT.md").exists())

        applied = agent_message(self.repo, "apply", run_id=run_id, confirmation=APPLY_CONFIRMATION)
        self.assertEqual(applied["status"]["status"], "APPLIED")
        self.assertTrue((self.repo / "PATCHBAY_MOCK_OUTPUT.md").exists())

    def test_agent_apply_does_not_ask_for_confirmation_before_gate_is_ready(self) -> None:
        planned = agent_message(self.repo, "not ready for apply")

        response = agent_message(self.repo, "apply", run_id=planned["run_id"])

        self.assertFalse(response["ok"])
        self.assertEqual(response["status"]["status"], "PLANNED")
        self.assertNotEqual(response["requires_confirmation"]["confirmation"], APPLY_CONFIRMATION)
        self.assertIn("Apply is blocked", response["reply"])

    def test_agent_does_not_apply_when_tests_are_skipped_by_default(self) -> None:
        self._write_mock_config(allow_without_tests=False)
        planned = agent_message(self.repo, "skip tests stays blocked")

        response = agent_message(self.repo, "approve", run_id=planned["run_id"], confirmation=PLAN_CONFIRMATION)

        self.assertTrue(response["ok"])
        self.assertEqual(response["status"]["status"], "REVIEWED_PASS")
        self.assertFalse(response["status"]["gate_state"]["ready_to_apply"])
        self.assertEqual(response["status"]["gate_state"]["tests_status"], "SKIPPED")
        self.assertIsNone(response["requires_confirmation"])

        apply_response = agent_message(self.repo, "apply", run_id=planned["run_id"])
        self.assertFalse(apply_response["ok"])
        self.assertIsNone(apply_response["requires_confirmation"])

    def test_mcp_patchbay_agent_wraps_same_service(self) -> None:
        from scripts.ai_flow import mcp_server

        original_root = mcp_server.ROOT
        try:
            mcp_server.ROOT = self.repo
            response = mcp_server.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": "patchbay_agent", "arguments": {"message": "mcp agent task"}},
                }
            )
        finally:
            mcp_server.ROOT = original_root

        payload = json.loads(response["result"]["content"][0]["text"])
        self.assertEqual(payload["status"]["status"], "PLANNED")
        self.assertEqual(payload["requires_confirmation"]["confirmation"], PLAN_CONFIRMATION)

    def test_mcp_patchbay_agent_can_run_doctor(self) -> None:
        from scripts.ai_flow import mcp_server

        original_root = mcp_server.ROOT
        try:
            mcp_server.ROOT = self.repo
            response = mcp_server.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": "patchbay_agent", "arguments": {"message": "readiness"}},
                }
            )
        finally:
            mcp_server.ROOT = original_root

        payload = json.loads(response["result"]["content"][0]["text"])
        self.assertEqual(payload["action"], "doctor")
        self.assertIn("checks", payload["doctor"])

    def test_cli_agent_message(self) -> None:
        response = self.cli_json("agent", "message", "cli agent task", "--include-plan")

        self.assertEqual(response["status"]["status"], "PLANNED")
        self.assertIn("PLAN.md", response["artifacts"])

    def test_cli_agent_doctor_message(self) -> None:
        response = self.cli_json("agent", "message", "readiness")

        self.assertEqual(response["action"], "doctor")
        self.assertIn("checks", response["doctor"])
        self.assertIsNone(response["run_id"])

    def test_agent_background_start_returns_pollable_job(self) -> None:
        response = agent_message(self.repo, "background agent plan", background=True)
        run_id = response["run_id"]
        run_path = self.repo / ".ai" / "runs" / run_id

        self.assertTrue(response["ok"])
        self.assertTrue(response["background"])
        self.assertEqual(response["job"]["phase"], "plan")
        self.assertEqual(response["next_actions"], ["status", "events"])
        self.assertTrue((run_path / "JOB.json").exists())
        self.assertTrue((run_path / "events.jsonl").exists())

    def test_agent_background_approval_requires_confirmation(self) -> None:
        planned = agent_message(self.repo, "background approval still gated")

        response = agent_message(self.repo, "approve", run_id=planned["run_id"], background=True)

        self.assertEqual(response["status"]["status"], "PLANNED")
        self.assertEqual(response["requires_confirmation"]["confirmation"], PLAN_CONFIRMATION)
        self.assertFalse((self.repo / ".ai" / "runs" / planned["run_id"] / "AGENT.lock").exists())

    def test_agent_background_continue_starts_agent_job(self) -> None:
        from scripts.ai_flow import agent as agent_module

        planned = agent_message(self.repo, "background autopilot")
        run_id = planned["run_id"]
        run_path = self.repo / ".ai" / "runs" / run_id

        class FakeProcess:
            pid = 9876

            def poll(self):
                return None

        with (
            mock.patch.object(agent_module.service, "resolve_root", return_value=self.repo),
            mock.patch.object(agent_module.subprocess, "Popen", return_value=FakeProcess()) as popen,
        ):
            response = agent_message(
                self.repo,
                "approve",
                run_id=run_id,
                confirmation=PLAN_CONFIRMATION,
                background=True,
            )

        self.assertTrue(response["background"])
        self.assertEqual(response["job"]["kind"], "agent")
        self.assertEqual(response["job"]["pid"], 9876)
        self.assertTrue((run_path / "AGENT.lock").exists())
        self.assertTrue((run_path / "JOB.json").exists())
        self.assertTrue(popen.call_args.kwargs["env"]["PATCHBAY_INHERITED_AGENT_LOCK"])

    def test_cli_background_agent_approval_completes_in_child_process(self) -> None:
        planned = agent_message(self.repo, "background child process")
        run_id = planned["run_id"]
        run_path = self.repo / ".ai" / "runs" / run_id

        response = self.cli_json(
            "agent",
            "message",
            "approve",
            "--run-id",
            run_id,
            "--confirmation",
            PLAN_CONFIRMATION,
            "--background",
        )

        self.assertTrue(response["background"])
        self.wait_for(lambda: not (run_path / "AGENT.lock").exists() and json.loads((run_path / "STATUS.json").read_text(encoding="utf-8"))["status"] == "REVIEWED_PASS")

        status = json.loads((run_path / "STATUS.json").read_text(encoding="utf-8"))
        self.assertEqual(status["status"], "REVIEWED_PASS")
        self.assertTrue(status["gate_state"]["ready_to_apply"] if "gate_state" in status else status["tests_passed"])

    def test_web_agent_message_endpoint(self) -> None:
        from scripts.ai_flow.web_server import create_server

        import threading

        server = create_server(self.repo, host="127.0.0.1", port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 2)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        host, port = server.server_address
        request = urllib.request.Request(
            f"http://{host}:{port}/api/agent/message",
            data=json.dumps({"message": "web agent task"}).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))

        self.assertEqual(payload["status"]["status"], "PLANNED")
        self.assertEqual(payload["requires_confirmation"]["confirmation"], PLAN_CONFIRMATION)


if __name__ == "__main__":
    unittest.main()
