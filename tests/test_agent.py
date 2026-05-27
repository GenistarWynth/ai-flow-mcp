from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import threading
import unittest
import urllib.parse
import urllib.request
from pathlib import Path

from scripts.ai_flow import service
from scripts.ai_flow.agent_server import create_agent_server


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
        self._write_mock_config()

    def tearDown(self) -> None:
        shutil.rmtree(self.tempdir, ignore_errors=True)

    def _write_mock_config(self) -> None:
        path = self.repo / ".ai" / "patchbay.toml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            """[phases.plan]
provider = "mock"

[phases.write]
provider = "mock"

[phases.review]
provider = "mock"

[phases.fix]
provider = "mock"

[commands_allowlist]
test = []
""",
            encoding="utf-8",
        )

    def _planned_run(self, task: str = "agent mock task") -> str:
        response = service.agent_message(self.repo, task)
        self.assertTrue(response["ok"])
        return response["run_id"]


class AgentWorkflowTests(AgentTestCase):
    def test_agent_new_message_returns_plan_and_plan_gate(self) -> None:
        response = service.agent_message(self.repo, "agent plans first")

        self.assertTrue(response["ok"])
        self.assertEqual(response["status"]["status"], "PLANNED")
        self.assertEqual(response["requires_confirmation"]["type"], "plan_approval")
        self.assertIn("PLAN.md", response["artifacts"])
        self.assertIn("Mock Implementation Plan", response["artifacts"]["PLAN.md"]["text"])

    def test_agent_refuses_approval_without_confirmation(self) -> None:
        run_id = self._planned_run()

        response = service.agent_message(self.repo, "approve the plan", run_id=run_id)

        self.assertEqual(response["status"]["status"], "PLANNED")
        self.assertEqual(response["requires_confirmation"]["confirmation"], "plan_approved")
        self.assertFalse((self.repo / ".ai" / "runs" / run_id / "APPROVAL.json").exists())

    def test_agent_approve_and_run_reaches_ready_to_apply(self) -> None:
        run_id = self._planned_run()

        response = service.agent_message(self.repo, "approve", run_id=run_id, confirmation="plan_approved")

        self.assertEqual(response["status"]["status"], "REVIEWED_PASS")
        self.assertTrue(response["status"]["gate_state"]["ready_to_apply"])
        self.assertEqual(response["requires_confirmation"]["type"], "apply_approval")
        self.assertFalse((self.repo / "PATCHBAY_MOCK_OUTPUT.md").exists())

    def test_agent_apply_requires_apply_confirmation(self) -> None:
        run_id = self._planned_run()
        service.agent_message(self.repo, "approve", run_id=run_id, confirmation="plan_approved")

        refused = service.agent_message(self.repo, "apply", run_id=run_id)
        self.assertEqual(refused["requires_confirmation"]["confirmation"], "apply_approved")
        self.assertFalse((self.repo / "PATCHBAY_MOCK_OUTPUT.md").exists())

        applied = service.agent_message(self.repo, "apply", run_id=run_id, confirmation="apply_approved")
        self.assertEqual(applied["status"]["status"], "APPLIED")
        self.assertTrue((self.repo / "PATCHBAY_MOCK_OUTPUT.md").exists())

    def test_agent_changes_requested_runs_bounded_fix_loop(self) -> None:
        run_id = self._planned_run("AI_FLOW_FORCE_CHANGES_REQUESTED")

        response = service.agent_message(self.repo, "approve", run_id=run_id, confirmation="plan_approved")

        self.assertEqual(response["status"]["status"], "REVIEWED_CHANGES_REQUESTED")
        self.assertEqual(response["status"]["fix_iterations"], 2)
        self.assertIn("上限", response["reply"])
        self.assertFalse(response["status"]["gate_state"]["ready_to_apply"])

    def test_agent_failure_returns_standard_response_with_artifacts(self) -> None:
        run_id = self._planned_run("agent failing test")
        run_path = self.repo / ".ai" / "runs" / run_id
        command = 'python -c "raise SystemExit(1)"'
        config = self.repo / ".ai" / "patchbay.toml"
        config.write_text(config.read_text(encoding="utf-8").replace("test = []", f"test = ['{command}']"), encoding="utf-8")
        plan = json.loads((run_path / "plan.json").read_text(encoding="utf-8"))
        plan["test_commands"] = [command]
        (run_path / "plan.json").write_text(json.dumps(plan), encoding="utf-8")

        response = service.agent_message(self.repo, "approve", run_id=run_id, confirmation="plan_approved")

        self.assertFalse(response["ok"])
        self.assertEqual(response["status"]["status"], "FAILED")
        self.assertEqual(response["status"]["stage"], "test")
        self.assertIn("TEST.log", response["artifacts"])


class AgentMcpAndCliTests(AgentTestCase):
    def test_mcp_tools_list_includes_patchbay_agent_schema(self) -> None:
        from scripts.ai_flow.mcp_server import handle

        response = handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        assert response is not None
        tools = {tool["name"]: tool for tool in response["result"]["tools"]}

        self.assertIn("patchbay_agent", tools)
        schema = tools["patchbay_agent"]["inputSchema"]
        self.assertIn("confirmation", schema["properties"])
        self.assertIn("include", schema["properties"])

    def test_cli_parser_accepts_agent_serve(self) -> None:
        from scripts.ai_flow.cli import build_parser

        args = build_parser().parse_args(["agent", "serve", "--host", "127.0.0.1", "--port", "8765", "--open"])

        self.assertEqual(args.command, "agent")
        self.assertEqual(args.agent_command, "serve")
        self.assertEqual(args.host, "127.0.0.1")
        self.assertEqual(args.port, 8765)
        self.assertTrue(args.open_browser)


class AgentHttpTests(AgentTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.server = create_agent_server(self.repo, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        super().tearDown()

    def _post_json(self, path: str, payload: dict) -> dict:
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            method="POST",
            headers={"content-type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))

    def _get_json(self, path: str, params: dict[str, str]) -> dict:
        query = urllib.parse.urlencode(params)
        with urllib.request.urlopen(f"{self.base_url}{path}?{query}", timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))

    def test_http_message_status_artifact_diff_and_sse(self) -> None:
        planned = self._post_json("/api/message", {"message": "http agent task"})
        run_id = planned["run_id"]

        status = self._get_json("/api/status", {"run_id": run_id, "since": "0"})
        self.assertEqual(status["status"]["status"], "PLANNED")

        artifact = self._get_json("/api/artifact", {"run_id": run_id, "name": "PLAN.md"})
        self.assertIn("Mock Implementation Plan", artifact["text"])

        diff = self._get_json("/api/diff", {"run_id": run_id})
        self.assertEqual(diff["diff"], "")

        query = urllib.parse.urlencode({"run_id": run_id, "since": "0"})
        with urllib.request.urlopen(f"{self.base_url}/api/events/stream?{query}", timeout=10) as response:
            body = response.read().decode("utf-8")
        self.assertIn("event: events", body)
        self.assertIn("plan", body)
