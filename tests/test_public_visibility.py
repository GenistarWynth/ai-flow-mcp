"""Tests for run listing, artifact reads, and background phase jobs."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock


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


class PublicVisibilityTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = Path(tempfile.mkdtemp(prefix="patchbay-visibility-"))
        self.repo = self.tempdir / "repo"
        self.repo.mkdir()
        run(["git", "init"], self.repo)
        run(["git", "config", "user.email", "patchbay@example.test"], self.repo)
        run(["git", "config", "user.name", "Patchbay tests"], self.repo)
        (self.repo / "README.md").write_text("# Visibility Repo\n", encoding="utf-8")
        (self.repo / ".gitignore").write_text(
            ".ai/runs/\n.ai/logs/\n.ai/worktrees/\n.ai/patchbay.toml\n.patchbay-worktrees/\n",
            encoding="utf-8",
        )
        run(["git", "add", "README.md", ".gitignore"], self.repo)
        run(["git", "commit", "-m", "initial"], self.repo)
        self.script = PROJECT_ROOT / "scripts" / "patchbay"

    def tearDown(self) -> None:
        shutil.rmtree(self.tempdir, ignore_errors=True)

    def cli_json(self, *args: str) -> dict:
        completed = run(["python", str(self.script), *args, "--json"], self.repo)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return json.loads(completed.stdout)

    def test_runs_lists_existing_runs(self) -> None:
        planned = self.cli_json("plan", "--task", "listable run", "--mock")

        result = self.cli_json("runs")

        self.assertTrue(any(item["run_id"] == planned["run_id"] for item in result["runs"]))
        self.assertGreaterEqual(result["count"], 1)

    def test_artifact_reads_and_tails_run_file(self) -> None:
        planned = self.cli_json("plan", "--task", "artifact read", "--mock")

        full = self.cli_json("artifact", planned["run_id"], "TASK.md")
        tail = self.cli_json("artifact", planned["run_id"], "TASK.md", "--tail", "1")

        self.assertEqual(full["artifact"], "TASK.md")
        self.assertIn("artifact read", full["text"])
        self.assertEqual(tail["lines_returned"], 1)

    def test_artifact_rejects_path_traversal(self) -> None:
        planned = self.cli_json("plan", "--task", "bad artifact", "--mock")
        completed = run(
            ["python", str(self.script), "artifact", planned["run_id"], "../STATUS.json", "--json"],
            self.repo,
        )

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("artifact name", completed.stderr.lower())

    def test_mcp_tools_include_runs_artifact_and_background_schema(self) -> None:
        from scripts.ai_flow.mcp_server import handle

        response = handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        assert response is not None
        tools = {tool["name"]: tool for tool in response["result"]["tools"]}
        self.assertIn("patchbay_runs", tools)
        self.assertIn("patchbay_artifact", tools)
        self.assertIn("patchbay_config_show", tools)
        self.assertIn("patchbay_config_phase_set", tools)
        self.assertIn("patchbay_config_command_set", tools)
        self.assertIn("patchbay_config_test_add", tools)
        self.assertIn("patchbay_config_provider_add_cli", tools)
        self.assertIn("background", tools["patchbay_plan"]["inputSchema"]["properties"])
        self.assertIn("background", tools["patchbay_write"]["inputSchema"]["properties"])

    def test_background_plan_returns_job_metadata(self) -> None:
        from scripts.ai_flow import service
        from scripts.ai_flow.mcp_server import patchbay_plan

        with mock.patch.object(service, "start_background_phase") as start:
            start.return_value = {
                "background": True,
                "phase": "plan",
                "pid": 123,
                "run_id": "20260524-background-task",
                "run_dir": str(self.repo / ".ai" / "runs" / "20260524-background-task"),
                "events_path": str(self.repo / ".ai" / "runs" / "20260524-background-task" / "events.jsonl"),
                "job": {"phase": "plan"},
            }

            result = patchbay_plan("background task", background=True)

        self.assertTrue(result["background"])
        self.assertEqual(result["phase"], "plan")
        self.assertEqual(result["pid"], 123)
        self.assertNotEqual(result["run_id"], "pending")
        self.assertTrue(result["events_path"].endswith("events.jsonl"))

    def test_background_plan_cli_returns_pollable_run_id(self) -> None:
        completed = run(
            ["python", str(self.script), "plan", "--task", "background pollable", "--mock", "--background", "--json"],
            self.repo,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)

        self.assertTrue(result["background"])
        self.assertNotEqual(result["run_id"], "pending")
        self.assertTrue(Path(result["run_dir"]).exists())
        self.assertTrue(Path(result["events_path"]).exists())

    def test_events_follow_json_returns_json_payload(self) -> None:
        planned = self.cli_json("plan", "--task", "follow json", "--mock")
        completed = run(
            ["python", str(self.script), "events", planned["run_id"], "--follow", "--json"],
            self.repo,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(result["run_id"], planned["run_id"])

    def test_status_exposes_current_phase_and_effective_providers(self) -> None:
        planned = self.cli_json("plan", "--task", "status detail", "--mock")

        status = self.cli_json("status", planned["run_id"])

        self.assertEqual(status["current_phase"], "plan")
        self.assertIn("effective_phase_providers", status)
        self.assertEqual(status["effective_phase_providers"]["plan"]["provider"], "claude_cli")
        self.assertEqual(status["effective_phase_providers"]["write"]["provider"], "reasonix_cli")
        self.assertIn("next_commands", status)
