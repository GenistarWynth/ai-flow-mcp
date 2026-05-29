"""Tests for config wizard producing valid .ai/patchbay.toml."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class ConfigWizardTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _make_git_repo(self) -> None:
        import subprocess
        subprocess.run(["git", "init"], cwd=str(self.tmp), capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "test@test"], cwd=str(self.tmp), capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "test"], cwd=str(self.tmp), capture_output=True, check=True)
        (self.tmp / "README.md").write_text("# test\n")
        subprocess.run(["git", "add", "."], cwd=str(self.tmp), capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=str(self.tmp), capture_output=True, check=True)

    def test_dry_write_toml_round_trips(self) -> None:
        """Verify that _write_toml produces a file load_config can read."""
        self._make_git_repo()
        from scripts.ai_flow.config_wizard import _write_toml

        config_path = self.tmp / ".ai" / "patchbay.toml"
        sections = {
            "models": {"planner": "claude-opus-4-7", "writer": "deepseek-v4-pro", "reviewer": "gpt-5.5"},
            "commands": {"claude": "claude", "codex": "codex"},
            "phases": {
                "plan": {"provider": "claude_cli", "model": "claude-opus-4-7"},
                "write": {"provider": "reasonix_cli", "model": "deepseek-v4-pro"},
                "review": {"provider": "codex_cli", "model": "gpt-5.5"},
                "fix": {},
                "test": {"commands": ["pytest -q"], "timeout": 900},
                "apply": {},
            },
            "workflow": {"require_plan_approval": True},
            "commands_allowlist": {"test": ["pytest -q"]},
        }
        _write_toml(config_path, sections)
        self.assertTrue(config_path.exists())

        from scripts.ai_flow.config import load_config
        cfg = load_config(self.tmp)
        self.assertEqual(cfg["models"]["planner"], "claude-opus-4-7")
        self.assertEqual(cfg["phases"]["plan"]["provider"], "claude_cli")
        self.assertEqual(cfg["phases"]["test"]["commands"], ["pytest -q"])

    def test_set_config_key(self) -> None:
        """Test non-interactive config.set."""
        from scripts.ai_flow.config_wizard import run_config_wizard
        self._make_git_repo()

        result = run_config_wizard(self.tmp, set_key="models.planner", set_value="gemini-2.5-pro")
        self.assertIn("set", result)
        self.assertEqual(result["set"]["models.planner"], "gemini-2.5-pro")

    def test_set_config_key_preserves_existing_comments(self) -> None:
        from scripts.ai_flow.config_wizard import run_config_wizard
        self._make_git_repo()
        config_path = self.tmp / ".ai" / "patchbay.toml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            "# keep this human note\n\n[models]\n# planner choice\nplanner = \"claude-opus-4-7\"\n",
            encoding="utf-8",
        )

        run_config_wizard(self.tmp, set_key="models.planner", set_value="gemini-2.5-pro")
        text = config_path.read_text(encoding="utf-8")

        self.assertIn("# keep this human note", text)
        self.assertIn("# planner choice", text)
        self.assertIn('planner = "gemini-2.5-pro"', text)

    def test_doctor_validates_phases(self) -> None:
        """Test doctor on valid default config."""
        from scripts.ai_flow.config import load_config
        from scripts.ai_flow.config_wizard import _run_doctor
        self._make_git_repo()
        cfg = load_config(self.tmp)
        result = _run_doctor(cfg)
        self.assertIn("plan", result["phases"])
        self.assertNotIn("error", result["phases"]["plan"])
        self.assertNotIn("error", result["phases"]["write"])
        self.assertNotIn("error", result["phases"]["review"])

    def test_show_returns_public_config(self) -> None:
        from scripts.ai_flow.config_wizard import run_config_wizard
        self._make_git_repo()

        result = run_config_wizard(self.tmp, show=True)
        self.assertIn("config", result)
        self.assertIn("resolved", result)

    def test_add_cli_provider(self) -> None:
        from scripts.ai_flow.config_wizard import run_config_wizard
        self._make_git_repo()

        result = run_config_wizard(
            self.tmp,
            provider_id="local_writer",
            provider_roles=["write", "fix"],
            provider_command="python",
            provider_args=["writer.py"],
            prompt_mode="stdin",
            output_contract="worktree_diff",
        )
        self.assertEqual(result["provider"], "local_writer")

    def test_add_command_and_test_command(self) -> None:
        from scripts.ai_flow.config_wizard import run_config_wizard
        self._make_git_repo()

        command_result = run_config_wizard(self.tmp, command_key_name="claude", command_value="claude")
        test_result = run_config_wizard(self.tmp, test_command="pytest -q")
        self.assertIn("commands.claude", command_result["set"])
        self.assertTrue(test_result["allowlisted"])

    def test_set_phase_configuration(self) -> None:
        from scripts.ai_flow.config_wizard import run_config_wizard
        self._make_git_repo()

        result = run_config_wizard(self.tmp, phase="plan", provider="mock", model="mock")
        self.assertEqual(result["phase"], "plan")
        self.assertEqual(result["updated"]["provider"], "mock")

    def test_set_bool_value(self) -> None:
        """Test setting a boolean config key."""
        from scripts.ai_flow.config_wizard import run_config_wizard
        self._make_git_repo()

        result = run_config_wizard(self.tmp, set_key="workflow.require_plan_approval", set_value="false")
        self.assertEqual(result["set"]["workflow.require_plan_approval"], False)

    def test_economy_profile_reports_four_phase_strategy(self) -> None:
        from scripts.ai_flow.config_wizard import run_config_wizard
        self._make_git_repo()

        result = run_config_wizard(self.tmp, profile="economy")
        status = result["status"]
        strategy = status["phase_strategy"]

        self.assertEqual(status["profile"], "economy")
        self.assertEqual(strategy["plan"]["tier"], "supervision")
        self.assertEqual(strategy["review"]["tier"], "supervision")
        self.assertEqual(strategy["write"]["tier"], "economy")
        self.assertEqual(strategy["fix"]["tier"], "economy")
        self.assertTrue(strategy["write"]["economy_route"])
        self.assertTrue(strategy["fix"]["economy_route"])
        self.assertEqual(strategy["write"]["model"], "deepseek-v4-pro")


if __name__ == "__main__":
    unittest.main()
