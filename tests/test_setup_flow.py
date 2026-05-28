from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock
from pathlib import Path


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


class SetupFlowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="patchbay-setup-"))
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        self.skills = self.tmp / "skills"
        self.script = PROJECT_ROOT / "scripts" / "patchbay"
        run(["git", "init"], self.repo)
        run(["git", "config", "user.email", "patchbay@example.test"], self.repo)
        run(["git", "config", "user.name", "Patchbay tests"], self.repo)
        (self.repo / "README.md").write_text("# setup repo\n", encoding="utf-8")
        run(["git", "add", "README.md"], self.repo)
        run(["git", "commit", "-m", "initial"], self.repo)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_setup_initializes_config_skill_and_doctor(self) -> None:
        from scripts.ai_flow.setup_flow import run_setup

        result = run_setup(self.repo, skill_path=self.skills, skip_mcp=True)

        self.assertTrue(result["ok"])
        self.assertTrue((self.repo / "AGENTS.md").exists())
        self.assertTrue((self.repo / ".ai" / "patchbay.example.toml").exists())
        self.assertTrue((self.repo / ".ai" / "patchbay.toml").exists())
        self.assertTrue((self.skills / "patchbay" / "SKILL.md").exists())
        self.assertTrue(result["config"]["created"])
        self.assertTrue(result["skill"]["installed"])
        self.assertTrue(result["doctor"]["ok"])

    def test_setup_dry_run_does_not_write_files(self) -> None:
        from scripts.ai_flow.setup_flow import run_setup

        result = run_setup(self.repo, skill_path=self.skills, skip_mcp=True, dry_run=True)

        self.assertFalse(result["ok"])
        self.assertTrue(result["dry_run"])
        self.assertTrue(result["config"]["would_create"])
        self.assertFalse((self.repo / "AGENTS.md").exists())
        self.assertFalse((self.repo / ".ai" / "patchbay.toml").exists())
        self.assertFalse((self.skills / "patchbay").exists())

    def test_cli_setup_json(self) -> None:
        completed = run(
            [
                "python",
                str(self.script),
                "setup",
                "--skill-path",
                str(self.skills),
                "--skip-mcp",
                "--json",
            ],
            self.repo,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertTrue(result["ok"])
        self.assertTrue((self.repo / ".ai" / "patchbay.toml").exists())
        self.assertTrue((self.skills / "patchbay" / "SKILL.md").exists())

    def test_setup_omits_manual_mcp_step_after_successful_registration(self) -> None:
        from scripts.ai_flow import setup_flow

        mcp_result = {
            "host": "codex",
            "command": "codex mcp add patchbay -- python scripts/patchbay_mcp_server.py",
            "executed": True,
            "exit_code": 0,
            "stdout": "",
            "stderr": "",
            "note": "MCP server registered successfully.",
        }
        with mock.patch.object(setup_flow, "run_mcp_install", return_value=mcp_result):
            result = setup_flow.run_setup(self.repo, skill_path=self.skills)

        self.assertIn("MCP server registered successfully.", result["next_actions"])
        self.assertFalse(any(str(item).startswith("Register the MCP server with:") for item in result["next_actions"]))

    def test_mcp_setup_tool_wraps_same_flow(self) -> None:
        from scripts.ai_flow import mcp_server

        original_root = mcp_server.ROOT
        try:
            mcp_server.ROOT = self.repo
            response = mcp_server.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {
                        "name": "patchbay_setup",
                        "arguments": {
                            "skill_path": str(self.skills),
                            "skip_mcp": True,
                        },
                    },
                }
            )
        finally:
            mcp_server.ROOT = original_root

        payload = json.loads(response["result"]["content"][0]["text"])
        self.assertTrue(payload["ok"])
        self.assertTrue((self.skills / "patchbay" / "SKILL.md").exists())


if __name__ == "__main__":
    unittest.main()
