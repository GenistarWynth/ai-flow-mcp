"""Tests for minimal custom CLI providers."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


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


class CustomProviderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = Path(tempfile.mkdtemp(prefix="patchbay-custom-provider-"))
        self.repo = self.tempdir / "repo"
        self.repo.mkdir()
        run(["git", "init"], self.repo)
        run(["git", "config", "user.email", "patchbay@example.test"], self.repo)
        run(["git", "config", "user.name", "Patchbay tests"], self.repo)
        (self.repo / "README.md").write_text("# Custom Provider Repo\n", encoding="utf-8")
        (self.repo / ".gitignore").write_text(
            ".ai/runs/\n.ai/logs/\n.ai/worktrees/\n.ai/patchbay.toml\n.patchbay-worktrees/\n",
            encoding="utf-8",
        )
        run(["git", "add", "README.md", ".gitignore"], self.repo)
        run(["git", "commit", "-m", "initial"], self.repo)
        (self.repo / ".ai").mkdir()

    def tearDown(self) -> None:
        shutil.rmtree(self.tempdir, ignore_errors=True)

    def test_custom_plan_provider_resolves_and_runs_cli_stdout(self) -> None:
        provider_script = self.tempdir / "planner.py"
        provider_script.write_text(
            """
import json
plan = {
  "version": 1,
  "summary": "custom plan",
  "requires_user_decision": False,
  "questions": [],
  "assumptions": [],
  "affected_files": [{"path": "CUSTOM.md", "operation": "create", "reason": "custom"}],
  "implementation_steps": [{"id": "S1", "description": "create file", "files": ["CUSTOM.md"], "verification": []}],
  "test_commands": [],
  "lint_commands": [],
  "typecheck_commands": [],
  "acceptance_criteria": [],
  "risks": [],
  "out_of_scope": [],
  "review_checklist": []
}
print("BEGIN_AI_FLOW_PLAN_JSON")
print(json.dumps(plan))
print("END_AI_FLOW_PLAN_JSON")
print("# Custom Plan")
""",
            encoding="utf-8",
        )
        python_cmd = sys.executable.replace("\\", "/")
        (self.repo / ".ai" / "patchbay.toml").write_text(
            f"""
[providers.local_planner]
roles = ["plan"]
command = "{python_cmd}"
args = ["{provider_script.as_posix()}"]
prompt_mode = "stdin"
output_contract = "plan_json"

[phases.plan]
provider = "local_planner"
""",
            encoding="utf-8",
        )

        from scripts.ai_flow import service
        from scripts.ai_flow.config import load_config, resolve_phase

        phase = resolve_phase(load_config(self.repo), "plan")
        self.assertEqual(phase["provider"], "local_planner")

        result = service.plan(self.repo, task="custom provider plan")
        self.assertEqual(result["summary"], "custom plan")

    def test_custom_writer_provider_captures_worktree_diff(self) -> None:
        writer_script = self.tempdir / "writer.py"
        writer_script.write_text(
            """
from pathlib import Path
Path("CUSTOM.md").write_text("# Custom writer\\n", encoding="utf-8")
print("custom writer wrote CUSTOM.md")
""",
            encoding="utf-8",
        )
        python_cmd = sys.executable.replace("\\", "/")
        (self.repo / ".ai" / "patchbay.toml").write_text(
            f"""
[providers.local_writer]
roles = ["write", "fix"]
command = "{python_cmd}"
args = ["{writer_script.as_posix()}"]
prompt_mode = "stdin"
output_contract = "worktree_diff"

[phases.write]
provider = "local_writer"

[commands_allowlist]
test = []
""",
            encoding="utf-8",
        )

        from scripts.ai_flow import service

        planned = service.plan(self.repo, task="custom writer", mock=True)
        service.approve(self.repo, planned["run_id"])
        written = service.write(self.repo, planned["run_id"])
        diff = service.diff(self.repo, planned["run_id"])

        self.assertEqual(written["status"], "IMPLEMENTED")
        self.assertIn("CUSTOM.md", diff)
