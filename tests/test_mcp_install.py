"""Tests for MCP host registration generation."""

from __future__ import annotations

import json
import tempfile
import unittest
import unittest.mock
from pathlib import Path
from textwrap import dedent


class McpInstallTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "scripts" / "patchbay_mcp_server.py").parent.mkdir(parents=True, exist_ok=True)
        (self.tmp / "scripts" / "patchbay_mcp_server.py").write_text(
            dedent(
                r'''
                import json
                import sys

                TOOLS = [
                    {"name": "patchbay_agent"},
                    {"name": "patchbay_plan"},
                    {"name": "patchbay_context"},
                    {"name": "patchbay_metrics"},
                    {"name": "patchbay_setup"},
                    {"name": "patchbay_install"},
                    {"name": "patchbay_doctor"},
                    {"name": "patchbay_events"},
                    {"name": "patchbay_apply"},
                ]

                for line in sys.stdin:
                    if not line.strip():
                        continue
                    message = json.loads(line)
                    method = message.get("method")
                    if "id" not in message:
                        continue
                    if method == "initialize":
                        result = {"serverInfo": {"name": "patchbay-test", "version": "0.0.0"}}
                    elif method == "tools/list":
                        result = {"tools": TOOLS}
                    else:
                        result = {}
                    print(json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": result}), flush=True)
                '''
            ).lstrip(),
            encoding="utf-8",
        )

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

    def test_codex_install_executes_command_when_available(self) -> None:
        from scripts.ai_flow import mcp_install
        import subprocess

        completed = subprocess.CompletedProcess(args=["codex"], returncode=0, stdout="ok\n", stderr="")
        with unittest.mock.patch.object(mcp_install.subprocess, "run", return_value=completed) as run_mock:
            result = mcp_install.install_codex(self.tmp, dry_run=False)

        self.assertTrue(result["executed"])
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(result["stdout"], "ok\n")
        self.assertEqual(result["stderr"], "")
        self.assertIn("codex mcp add patchbay", result["command"])
        self.assertTrue(run_mock.called)
        argv = run_mock.call_args.args[0]
        self.assertEqual(argv[:4], ["codex", "mcp", "add", "patchbay"])
        self.assertIn("--", argv)

    def test_codex_install_falls_back_when_cli_missing(self) -> None:
        from scripts.ai_flow import mcp_install

        with unittest.mock.patch.object(mcp_install.subprocess, "run", side_effect=FileNotFoundError("codex not found")):
            result = mcp_install.install_codex(self.tmp, dry_run=False)

        self.assertFalse(result["executed"])
        self.assertIn("codex not found", result["error"])
        self.assertIn("codex mcp add patchbay", result["command"])

    def test_codex_install_falls_back_when_cli_cannot_execute(self) -> None:
        from scripts.ai_flow import mcp_install

        with unittest.mock.patch.object(mcp_install.subprocess, "run", side_effect=PermissionError("codex denied")):
            result = mcp_install.install_codex(self.tmp, dry_run=False)

        self.assertFalse(result["executed"])
        self.assertIn("codex denied", result["error"])
        self.assertIn("codex mcp add patchbay", result["command"])

    def test_codex_install_treats_existing_registration_as_success(self) -> None:
        from scripts.ai_flow import mcp_install
        import subprocess

        completed = subprocess.CompletedProcess(args=["codex"], returncode=1, stdout="", stderr="server patchbay already exists\n")
        with unittest.mock.patch.object(mcp_install.subprocess, "run", return_value=completed):
            result = mcp_install.install_codex(self.tmp, dry_run=False)

        self.assertTrue(result["executed"])
        self.assertTrue(result["already_registered"])
        self.assertIsNone(result["error"])

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
        self.assertTrue(result["server_reachable"])
        self.assertTrue(result["required_tools_present"])
        self.assertEqual(result["missing_tools"], [])
        self.assertEqual(result["server_info"]["name"], "patchbay-test")

    def test_mcp_doctor_probes_stdio_server(self) -> None:
        from scripts.ai_flow import mcp_install

        with unittest.mock.patch.object(
            mcp_install,
            "_probe_mcp_server",
            return_value={
                "ok": True,
                "tool_count": 21,
                "required_tools_present": True,
                "missing_tools": [],
                "server_info": {"name": "patchbay"},
                "error": None,
            },
        ) as probe:
            result = mcp_install.run_mcp_doctor(self.tmp)

        probe.assert_called_once()
        self.assertTrue(result["server_reachable"])
        self.assertEqual(result["tool_count"], 21)
        self.assertTrue(result["required_tools_present"])

    def test_mcp_doctor_includes_root(self) -> None:
        from scripts.ai_flow.mcp_install import run_mcp_doctor
        result = run_mcp_doctor(self.tmp)
        self.assertTrue(result["server_command"].endswith(f"--root {self.tmp}"))


if __name__ == "__main__":
    unittest.main()
