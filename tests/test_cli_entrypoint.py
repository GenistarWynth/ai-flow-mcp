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
        self.assertIn("status", help_text)
        self.assertIn("events", help_text)
        self.assertIn("config", help_text)
        self.assertIn("mcp", help_text)
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

    def test_mcp_server_module_imports(self) -> None:
        """The MCP server module should be importable."""
        from scripts.ai_flow.mcp_server import handle, main, TOOLS
        self.assertIsNotNone(handle)
        self.assertIsNotNone(main)
        self.assertIn("patchbay_plan", TOOLS)
        self.assertIn("patchbay_events", TOOLS)
        self.assertIn("ai_flow_plan", TOOLS)
        self.assertIn("ai_flow_events", TOOLS)

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
        self.assertIn("patchbay_events", tool_names)
        self.assertIn("ai_flow_events", tool_names)


if __name__ == "__main__":
    unittest.main()
