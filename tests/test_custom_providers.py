"""Tests for minimal custom CLI providers."""

from __future__ import annotations

import json
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
        from scripts.ai_flow.adapters import reset_custom_providers

        reset_custom_providers()
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
import json
import os
import sys
from pathlib import Path
Path("CUSTOM.md").write_text("# Custom writer\\n", encoding="utf-8")
Path(os.environ["PATCHBAY_USAGE_FILE"]).write_text(json.dumps({
    "usage": {"input_tokens": 10, "output_tokens": 5},
    "total_cost_usd": 0.001,
}, indent=2), encoding="utf-8")
print("custom writer wrote CUSTOM.md")
print(json.dumps({"usage": {"cached_tokens": 2}}), file=sys.stderr)
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
        metrics = service.metrics(self.repo, planned["run_id"])["run_metrics"]

        self.assertEqual(written["status"], "IMPLEMENTED")
        self.assertIn("CUSTOM.md", diff)
        self.assertEqual(metrics["token_usage"]["input_tokens"], 10)
        self.assertEqual(metrics["token_usage"]["output_tokens"], 5)
        self.assertEqual(metrics["token_usage"]["cached_tokens"], 2)
        self.assertEqual(metrics["token_usage"]["total_tokens"], 17)
        self.assertEqual(metrics["cost"]["estimated_total"], 0.001)

    def test_custom_fix_only_provider_uses_fix_registry(self) -> None:
        fixer_script = self.tempdir / "fixer.py"
        fixer_script.write_text(
            """
from pathlib import Path
Path("FIXED.md").write_text("# Custom fixer\\n", encoding="utf-8")
print("custom fixer wrote FIXED.md")
""",
            encoding="utf-8",
        )
        python_cmd = sys.executable.replace("\\", "/")
        (self.repo / ".ai" / "patchbay.toml").write_text(
            f"""
[providers.local_fixer]
roles = ["fix"]
command = "{python_cmd}"
args = ["{fixer_script.as_posix()}"]
prompt_mode = "stdin"
output_contract = "worktree_diff"

[phases.write]
provider = "mock"

[phases.fix]
provider = "local_fixer"

[commands_allowlist]
test = []
""",
            encoding="utf-8",
        )

        from scripts.ai_flow import service

        planned = service.plan(self.repo, task="custom fixer", mock=True)
        service.approve(self.repo, planned["run_id"])
        service.write(self.repo, planned["run_id"], mock=True)
        run_path = self.repo / ".ai" / "runs" / planned["run_id"]
        status = service.status(self.repo, planned["run_id"])
        status["status"] = "REVIEWED_CHANGES_REQUESTED"
        (run_path / "STATUS.json").write_text(json.dumps(status), encoding="utf-8")
        (run_path / "REVIEW.md").write_text("CHANGES_REQUESTED\n\nRequired Fixes:\n1. Use local fixer.\n", encoding="utf-8")

        fixed = service.fix(self.repo, planned["run_id"])
        diff = service.diff(self.repo, planned["run_id"])

        self.assertEqual(fixed["status"], "IMPLEMENTED")
        self.assertIn("FIXED.md", diff)
        self.assertIn("custom fixer wrote FIXED.md", (run_path / "writer.log").read_text(encoding="utf-8"))

    def test_custom_provider_registry_is_scoped_to_loaded_config(self) -> None:
        provider_script = self.tempdir / "writer.py"
        provider_script.write_text("print('noop')\n", encoding="utf-8")
        python_cmd = sys.executable.replace("\\", "/")
        (self.repo / ".ai" / "patchbay.toml").write_text(
            f"""
[providers.local_writer]
roles = ["write"]
command = "{python_cmd}"
args = ["{provider_script.as_posix()}"]
prompt_mode = "stdin"
output_contract = "writer_diff"
""",
            encoding="utf-8",
        )

        from scripts.ai_flow.adapters import WRITERS
        from scripts.ai_flow.config import load_config

        load_config(self.repo)
        self.assertIn("local_writer", WRITERS)

        other_repo = self.tempdir / "other-repo"
        other_repo.mkdir()
        (other_repo / ".ai").mkdir()
        load_config(other_repo)

        self.assertEqual(set(WRITERS), {"reasonix_cli", "mock"})
