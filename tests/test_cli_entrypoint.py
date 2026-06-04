"""Smoke tests for CLI entrypoint parity."""

from __future__ import annotations

import unittest


class CliEntrypointTest(unittest.TestCase):
    def test_cli_module_imports(self) -> None:
        """Verify the CLI module can be imported without errors."""
        from scripts.ai_flow.cli import build_parser, main
        self.assertIsNotNone(build_parser)
        self.assertIsNotNone(main)

    def test_build_parser_has_all_commands(self) -> None:
        from scripts.ai_flow.cli import build_parser
        parser = build_parser()
        # Parse help to verify subcommands are registered
        help_text = parser.format_help()
        self.assertIn("plan", help_text)
        self.assertIn("write", help_text)
        self.assertIn("review", help_text)
        self.assertIn("doctor", help_text)
        self.assertIn("setup", help_text)
        self.assertIn("install", help_text)
        self.assertIn("status", help_text)
        self.assertIn("events", help_text)
        self.assertIn("metrics", help_text)
        self.assertIn("config", help_text)
        self.assertIn("mcp", help_text)
        self.assertIn("agent", help_text)
        self.assertIn("skill", help_text)
        self.assertIn("apply", help_text)
        self.assertIn("diff", help_text)
        self.assertIn("cleanup", help_text)

    def test_main_help_exits_zero(self) -> None:
        from scripts.ai_flow.cli import main
        try:
            main(["--help"])
        except SystemExit as e:
            self.assertEqual(e.code, 0)

    def test_main_no_command_exits_nonzero(self) -> None:
        from scripts.ai_flow.cli import main
        try:
            main([])
        except SystemExit as e:
            self.assertNotEqual(e.code, 0)

    def test_console_scripts_declared(self) -> None:
        """pyproject exposes both CLI and MCP console scripts."""
        import tomllib
        from pathlib import Path

        data = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
        scripts = data["project"]["scripts"]
        self.assertEqual(scripts["patchbay"], "ai_flow.cli:main")
        self.assertEqual(scripts["patchbay-mcp"], "patchbay_mcp_server:main")

    def test_patchbay_mcp_console_target_exists(self) -> None:
        import importlib.util
        from pathlib import Path

        spec = importlib.util.spec_from_file_location(
            "patchbay_mcp_server",
            Path("scripts/patchbay_mcp_server.py"),
        )
        self.assertIsNotNone(spec)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        self.assertTrue(callable(getattr(module, "main", None)))

    def test_mcp_install_parser_accepts_root_and_claude_code(self) -> None:
        import contextlib
        import io

        from scripts.ai_flow.cli import build_parser

        parser = build_parser()
        args = parser.parse_args(["mcp", "install", "claude-code", "--root", "C:/tmp/repo", "--dry-run"])
        self.assertEqual(args.host, "claude-code")
        self.assertEqual(args.root, "C:/tmp/repo")

        alias_args = parser.parse_args(["mcp", "install", "Claude Desktop", "--dry-run"])
        self.assertEqual(alias_args.host, "Claude Desktop")
        self.assertTrue(alias_args.dry_run)

        help_output = io.StringIO()
        with self.assertRaises(SystemExit) as exit_info, contextlib.redirect_stdout(help_output):
            parser.parse_args(["mcp", "install", "--help"])
        self.assertEqual(exit_info.exception.code, 0)
        self.assertIn("claude-code", help_output.getvalue())
        self.assertIn("Claude Desktop", help_output.getvalue())

    def test_mcp_server_module_imports(self) -> None:
        """The MCP server module should be importable."""
        from scripts.ai_flow.mcp_server import handle, main, TOOLS
        self.assertIsNotNone(handle)
        self.assertIsNotNone(main)
        self.assertIn("patchbay_plan", TOOLS)
        self.assertIn("patchbay_agent", TOOLS)
        self.assertIn("patchbay_setup", TOOLS)
        self.assertIn("patchbay_install", TOOLS)
        self.assertIn("patchbay_events", TOOLS)
        self.assertIn("patchbay_metrics", TOOLS)
        self.assertIn("patchbay_doctor", TOOLS)
        self.assertIn("patchbay_skill_install", TOOLS)
        self.assertIn("patchbay_skill_print", TOOLS)
        self.assertIn("patchbay_skill_doctor", TOOLS)
        self.assertIn("patchbay_config_show", TOOLS)
        self.assertIn("patchbay_config_phase_set", TOOLS)
        self.assertIn("patchbay_config_command_set", TOOLS)
        self.assertIn("patchbay_config_test_add", TOOLS)
        self.assertIn("patchbay_config_profile_apply", TOOLS)
        self.assertIn("patchbay_config_profile_show", TOOLS)
        self.assertIn("patchbay_config_provider_add_cli", TOOLS)
        self.assertIn("ai_flow_plan", TOOLS)
        self.assertIn("ai_flow_agent", TOOLS)
        self.assertIn("ai_flow_setup", TOOLS)
        self.assertIn("ai_flow_install", TOOLS)
        self.assertIn("ai_flow_events", TOOLS)
        self.assertIn("ai_flow_metrics", TOOLS)
        self.assertIn("ai_flow_doctor", TOOLS)
        self.assertIn("ai_flow_skill_install", TOOLS)
        self.assertIn("ai_flow_skill_print", TOOLS)
        self.assertIn("ai_flow_skill_doctor", TOOLS)
        self.assertIn("ai_flow_config_profile_apply", TOOLS)
        self.assertIn("ai_flow_config_profile_show", TOOLS)

    def test_skill_parser_accepts_codex_aliases(self) -> None:
        import contextlib
        import io

        from scripts.ai_flow.cli import build_parser

        parser = build_parser()
        install = parser.parse_args(["skill", "install", "Codex Desktop", "--dry-run", "--json"])
        self.assertEqual(install.host, "Codex Desktop")
        self.assertTrue(install.dry_run)

        doctor = parser.parse_args(["skill", "doctor", "Codex 桌面", "--path", "C:/tmp/skills", "--json"])
        self.assertEqual(doctor.host, "Codex 桌面")
        self.assertEqual(doctor.path, "C:/tmp/skills")

        help_output = io.StringIO()
        with self.assertRaises(SystemExit) as exit_info, contextlib.redirect_stdout(help_output):
            parser.parse_args(["skill", "install", "--help"])
        self.assertEqual(exit_info.exception.code, 0)
        self.assertIn("Codex Desktop", help_output.getvalue())
        self.assertIn("Codex 桌面", help_output.getvalue())

    def test_mcp_initialize(self) -> None:
        from scripts.ai_flow.mcp_server import handle
        response = handle({"method": "initialize", "id": 1, "params": {}})
        self.assertIsNotNone(response)
        assert response is not None
        self.assertIn("result", response)
        self.assertEqual(response["result"]["serverInfo"]["name"], "patchbay")

    def test_mcp_tools_list_includes_new_tools(self) -> None:
        from scripts.ai_flow.mcp_server import handle
        response = handle({"method": "tools/list", "id": 2, "params": {}})
        self.assertIsNotNone(response)
        assert response is not None
        tool_names = [t["name"] for t in response["result"]["tools"]]
        self.assertIn("patchbay_agent", tool_names)
        self.assertIn("patchbay_setup", tool_names)
        self.assertIn("patchbay_install", tool_names)
        self.assertIn("patchbay_events", tool_names)
        self.assertIn("patchbay_metrics", tool_names)
        self.assertIn("patchbay_doctor", tool_names)
        self.assertIn("patchbay_cancel", tool_names)
        self.assertIn("patchbay_skill_install", tool_names)
        self.assertIn("patchbay_skill_print", tool_names)
        self.assertIn("patchbay_skill_doctor", tool_names)
        self.assertIn("patchbay_config_profile_apply", tool_names)
        self.assertIn("patchbay_config_profile_show", tool_names)
        self.assertIn("ai_flow_agent", tool_names)
        self.assertIn("ai_flow_setup", tool_names)
        self.assertIn("ai_flow_install", tool_names)
        self.assertIn("ai_flow_events", tool_names)
        self.assertIn("ai_flow_metrics", tool_names)
        self.assertIn("ai_flow_doctor", tool_names)
        self.assertIn("ai_flow_cancel", tool_names)
        self.assertIn("ai_flow_skill_install", tool_names)
        self.assertIn("ai_flow_skill_print", tool_names)
        self.assertIn("ai_flow_skill_doctor", tool_names)
        self.assertIn("ai_flow_config_profile_apply", tool_names)
        self.assertIn("ai_flow_config_profile_show", tool_names)

    def test_agent_and_skill_parsers(self) -> None:
        from scripts.ai_flow.cli import build_parser

        parser = build_parser()
        doctor = parser.parse_args(["doctor", "--root", "C:/tmp/repo", "--host", "claude-desktop", "--probe-mcp", "--json"])
        self.assertEqual(doctor.command, "doctor")
        self.assertEqual(doctor.root, "C:/tmp/repo")
        self.assertEqual(doctor.host, "claude-desktop")
        self.assertFalse(doctor.skip_mcp)
        self.assertTrue(doctor.probe_mcp)

        local_doctor = parser.parse_args(["doctor", "--local-only", "--json"])
        self.assertEqual(local_doctor.command, "doctor")
        self.assertTrue(local_doctor.skip_mcp)
        no_mcp_doctor = parser.parse_args(["doctor", "--no-mcp", "--json"])
        self.assertTrue(no_mcp_doctor.skip_mcp)

        cancel = parser.parse_args(["cancel", "run-1", "--json"])
        self.assertEqual(cancel.command, "cancel")
        self.assertEqual(cancel.run_id, "run-1")

        setup = parser.parse_args(["setup", "--host", "codex", "--skill-path", "C:/tmp/skills", "--skip-mcp", "--json"])
        self.assertEqual(setup.command, "setup")
        self.assertEqual(setup.host, "codex")
        self.assertEqual(setup.skill_path, "C:/tmp/skills")
        self.assertTrue(setup.skip_mcp)
        local_setup = parser.parse_args(["setup", "--local-only", "--json"])
        self.assertTrue(local_setup.skip_mcp)
        no_mcp_setup = parser.parse_args(["setup", "--no-mcp", "--json"])
        self.assertTrue(no_mcp_setup.skip_mcp)

        install = parser.parse_args(["install", "--host", "codex", "--skill-path", "C:/tmp/skills", "--skip-mcp", "--json"])
        self.assertEqual(install.command, "install")
        self.assertEqual(install.host, "codex")
        self.assertEqual(install.skill_path, "C:/tmp/skills")
        self.assertTrue(install.skip_mcp)
        local_install = parser.parse_args(["install", "--local-only", "--json"])
        self.assertTrue(local_install.skip_mcp)

        agent = parser.parse_args(["agent", "message", "continue", "--run-id", "run-1", "--confirmation", "plan_approved", "--background", "--json"])
        self.assertEqual(agent.command, "agent")
        self.assertEqual(agent.agent_command, "message")
        self.assertEqual(agent.run_id, "run-1")
        self.assertEqual(agent.confirmation, "plan_approved")
        self.assertTrue(agent.background)

        skill = parser.parse_args(["skill", "install", "codex", "--dry-run", "--json"])
        self.assertEqual(skill.command, "skill")
        self.assertEqual(skill.skill_command, "install")
        self.assertEqual(skill.host, "codex")
        self.assertTrue(skill.dry_run)

        skill_doctor = parser.parse_args(["skill", "doctor", "codex", "--path", "C:/tmp/skills", "--json"])
        self.assertEqual(skill_doctor.command, "skill")
        self.assertEqual(skill_doctor.skill_command, "doctor")
        self.assertEqual(skill_doctor.host, "codex")
        self.assertEqual(skill_doctor.path, "C:/tmp/skills")

        profile = parser.parse_args(["config", "profile", "apply", "economy", "--json"])
        self.assertEqual(profile.command, "config")
        self.assertEqual(profile.config_command, "profile")
        self.assertEqual(profile.profile_command, "apply")
        self.assertEqual(profile.profile, "economy")

        provider = parser.parse_args([
            "config",
            "provider",
            "add-cli",
            "cheap_writer",
            "--roles",
            "write",
            "fix",
            "--command",
            "deepseek-writer",
            "--output-contract",
            "writer_diff",
            "--activate-economy",
            "--economy-model",
            "deepseek-chat",
            "--economy-label",
            "DeepSeek cheap writer",
            "--json",
        ])
        self.assertEqual(provider.command, "config")
        self.assertEqual(provider.config_command, "provider")
        self.assertTrue(provider.activate_economy)
        self.assertEqual(provider.economy_model, "deepseek-chat")
        self.assertEqual(provider.economy_label, "DeepSeek cheap writer")

    def test_cli_doctor_skips_stdio_mcp_probe_by_default(self) -> None:
        from pathlib import Path
        from unittest import mock

        from scripts.ai_flow import cli

        parser = cli.build_parser()
        with mock.patch.object(cli, "run_doctor", return_value={"ok": True}) as doctor:
            cli.dispatch(parser.parse_args(["doctor", "--json"]), Path.cwd())
            self.assertFalse(doctor.call_args.kwargs["include_mcp"])
            self.assertFalse(doctor.call_args.kwargs["suppress_mcp_actions"])

            cli.dispatch(parser.parse_args(["doctor", "--probe-mcp", "--json"]), Path.cwd())
            self.assertTrue(doctor.call_args.kwargs["include_mcp"])
            self.assertFalse(doctor.call_args.kwargs["suppress_mcp_actions"])

            cli.dispatch(parser.parse_args(["doctor", "--local-only", "--probe-mcp", "--json"]), Path.cwd())
            self.assertFalse(doctor.call_args.kwargs["include_mcp"])
            self.assertTrue(doctor.call_args.kwargs["suppress_mcp_actions"])


if __name__ == "__main__":
    unittest.main()
