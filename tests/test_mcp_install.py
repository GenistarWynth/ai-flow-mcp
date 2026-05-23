"""Tests for MCP host registration generation."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path


class McpInstallTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "scripts" / "patchbay_mcp_server.py").parent.mkdir(parents=True, exist_ok=True)
        (self.tmp / "scripts" / "patchbay_mcp_server.py").write_text("# stub\n")

        import subprocess
        subprocess.run(["git", "init"], cwd=str(self.tmp), capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "test@test"], cwd=str(self.tmp), capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "test"], cwd=str(self.tmp), capture_output=True, check=True)
        (self.tmp / "README.md").write_text("# test\n")
        subprocess.run(["git", "add", "."], cwd=str(self.tmp), capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=str(self.tmp), capture_output=True, check=True)

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_codex_dry_run_returns_command(self) -> None:
        from scripts.ai_flow.mcp_install import install_codex
        result = install_codex(self.tmp, dry_run=True)
        self.assertEqual(result["host"], "codex")
        self.assertIn("codex mcp add patchbay", result["command"])
        self.assertTrue(result["dry_run"])

    def test_claude_dry_run_returns_command(self) -> None:
        from scripts.ai_flow.mcp_install import install_claude
        result = install_claude(self.tmp, dry_run=True)
        self.assertEqual(result["host"], "claude")
        self.assertIn("claude mcp add patchbay", result["command"])

    def test_claude_code_dry_run_returns_command(self) -> None:
        from scripts.ai_flow.mcp_install import run_mcp_install
        result = run_mcp_install(self.tmp, "claude-code", dry_run=True)
        self.assertEqual(result["host"], "claude-code")
        self.assertIn("claude mcp add patchbay", result["command"])

    def test_gemini_dry_run_returns_command(self) -> None:
        from scripts.ai_flow.mcp_install import install_gemini
        result = install_gemini(self.tmp, dry_run=True)
        self.assertEqual(result["host"], "gemini")
        self.assertIn("gemini", result["command"])

    def test_claude_desktop_dry_run_returns_entry(self) -> None:
        from scripts.ai_flow.mcp_install import install_claude_desktop
        result = install_claude_desktop(self.tmp, dry_run=True)
        self.assertEqual(result["host"], "claude-desktop")
        self.assertIn("entry", result)
        self.assertIn("command", result["entry"])
        self.assertIn("args", result["entry"])

    def test_claude_desktop_writes_config(self) -> None:
        from scripts.ai_flow.mcp_install import install_claude_desktop, _claude_desktop_config_path

        # Override config path to tmp to avoid touching real config
        import scripts.ai_flow.mcp_install as mod
        original = mod._claude_desktop_config_path
        config_file = self.tmp / "claude_desktop_config.json"
        mod._claude_desktop_config_path = lambda: config_file
        try:
            result = install_claude_desktop(self.tmp, dry_run=False)
            self.assertFalse(result.get("dry_run"))
            self.assertTrue(config_file.exists())
            parsed = json.loads(config_file.read_text())
            self.assertIn("patchbay", parsed.get("mcpServers", {}))
        finally:
            mod._claude_desktop_config_path = original

    def test_unknown_host_raises(self) -> None:
        from scripts.ai_flow.mcp_install import run_mcp_install
        from scripts.ai_flow.errors import AiFlowError
        with self.assertRaises(AiFlowError):
            run_mcp_install(self.tmp, "nonexistent")

    def test_mcp_doctor(self) -> None:
        from scripts.ai_flow.mcp_install import run_mcp_doctor
        result = run_mcp_doctor(self.tmp)
        self.assertIn("server_command", result)
        self.assertTrue(result["server_script_exists"])
        self.assertIn("codex", result["supported_hosts"])

    def test_mcp_doctor_includes_root(self) -> None:
        from scripts.ai_flow.mcp_install import run_mcp_doctor
        result = run_mcp_doctor(self.tmp)
        self.assertTrue(result["server_command"].endswith(f"--root {self.tmp}"))


if __name__ == "__main__":
    unittest.main()
