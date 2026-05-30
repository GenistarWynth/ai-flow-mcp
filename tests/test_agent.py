from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

from scripts.ai_flow.agent import APPLY_CONFIRMATION, PLAN_CONFIRMATION, agent_message


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str], cwd: Path, *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(cwd),
        env=env,
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
        self.script = PROJECT_ROOT / "scripts" / "patchbay"
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
        self._write_mock_config(allow_without_tests=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.tempdir, ignore_errors=True)

    def _write_mock_config(self, *, allow_without_tests: bool) -> None:
        path = self.repo / ".ai" / "patchbay.toml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f"""[phases.plan]
provider = "mock"

[phases.write]
provider = "mock"

[phases.review]
provider = "mock"

[phases.fix]
provider = "mock"

[workflow]
allow_apply_without_tests = {str(allow_without_tests).lower()}

[commands_allowlist]
test = []
""",
            encoding="utf-8",
        )

    def cli_json(self, *args: str, env: dict[str, str] | None = None) -> dict:
        full_env = None
        if env is not None:
            full_env = os.environ.copy()
            full_env.update(env)
        completed = run(["python", str(self.script), *args, "--json"], self.repo, env=full_env)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return json.loads(completed.stdout)

    def wait_for(self, predicate, *, timeout: float = 8.0):
        deadline = time.time() + timeout
        last = None
        while time.time() < deadline:
            last = predicate()
            if last:
                return last
            time.sleep(0.1)
        self.fail(f"Timed out waiting for condition; last value: {last!r}")

    def _set_reasonix_command_to_python(self) -> None:
        config_path = self.repo / ".ai" / "patchbay.toml"
        escaped = sys.executable.replace("\\", "\\\\")
        with config_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(f'\n[commands]\nreasonix = "{escaped}"\n')


class AgentWorkflowTests(AgentTestCase):
    def test_agent_new_message_returns_plan_and_gate(self) -> None:
        response = agent_message(self.repo, "agent plans first")

        self.assertTrue(response["ok"])
        self.assertEqual(response["status"]["status"], "PLANNED")
        self.assertEqual(response["requires_confirmation"]["confirmation"], PLAN_CONFIRMATION)
        self.assertIn("PLAN.md", response["artifacts"])
        self.assertIn("Mock Implementation Plan", response["artifacts"]["PLAN.md"]["text"])
        self.assertEqual(response["context"]["next_actions"][0]["name"], "approve")

    def test_agent_doctor_message_returns_readiness_without_starting_run(self) -> None:
        response = agent_message(self.repo, "doctor")

        self.assertEqual(response["action"], "doctor")
        self.assertIn("doctor", response)
        self.assertIn("checks", response["doctor"])
        self.assertIsNone(response["run_id"])
        self.assertFalse((self.repo / ".ai" / "runs").exists())

    def test_agent_doctor_message_can_target_mcp_host(self) -> None:
        desktop = agent_message(self.repo, "readiness for Claude Desktop")
        gemini = agent_message(self.repo, "检查 Gemini 命令行环境")

        self.assertEqual(desktop["action"], "doctor")
        self.assertEqual(desktop["setup_host"], "claude-desktop")
        self.assertEqual(desktop["doctor"]["host"], "claude-desktop")
        desktop_actions = {item["id"]: item for item in desktop["actions"]}
        self.assertEqual(desktop_actions["probe_mcp"]["host"], "claude-desktop")
        self.assertIn("--host claude-desktop", desktop_actions["probe_mcp"]["command"])
        self.assertEqual(gemini["setup_host"], "gemini")
        self.assertEqual(gemini["doctor"]["host"], "gemini")
        self.assertIsNone(desktop["run_id"])
        self.assertFalse((self.repo / ".ai" / "runs").exists())

    def test_agent_doctor_surfaces_non_blocking_recommendations(self) -> None:
        response = agent_message(self.repo, "readiness")

        self.assertEqual(response["action"], "doctor")
        self.assertTrue(any("config profile apply economy" in item for item in response["recommendations"]))
        self.assertIn("apply economy profile", response["next_actions"])
        self.assertTrue(any(action["id"] == "apply_economy_profile" for action in response["actions"]))
        self.assertIn("Recommendations:", response["reply"])

    def test_agent_chinese_environment_check_returns_readiness_without_starting_run(self) -> None:
        for message in ("检查环境", "环境检查", "环境自检", "项目自检"):
            with self.subTest(message=message):
                response = agent_message(self.repo, message)

                self.assertEqual(response["action"], "doctor")
                self.assertIsNone(response["run_id"])

        self.assertFalse((self.repo / ".ai" / "runs").exists())

    def test_agent_doctor_does_not_reapply_economy_when_reasonix_command_is_missing(self) -> None:
        config_path = self.repo / ".ai" / "patchbay.toml"
        config_path.write_text(
            """[commands]
reasonix = ""

[phases.plan]
provider = "mock"

[phases.write]
provider = "reasonix_cli"
model = "deepseek-v4-pro"
command_key = "reasonix"

[phases.review]
provider = "mock"

[phases.fix]
provider = "reasonix_cli"
model = "deepseek-v4-pro"
command_key = "reasonix"

[workflow]
allow_apply_without_tests = true

[commands_allowlist]
test = []
""",
            encoding="utf-8",
        )

        response = agent_message(self.repo, "readiness")

        self.assertEqual(response["action"], "doctor")
        self.assertTrue(any("commands.reasonix" in item for item in response["recommendations"]))
        self.assertIn("configure reasonix command", response["next_actions"])
        self.assertNotIn("apply economy profile", response["next_actions"])
        actions = {item["id"]: item for item in response["actions"]}
        self.assertEqual(actions["configure_reasonix_command"]["kind"], "local_agent")
        self.assertEqual(actions["configure_reasonix_command"]["message"], "configure reasonix command")
        self.assertNotIn("apply_economy_profile", actions)

    def test_agent_can_show_and_apply_economy_profile_without_starting_run(self) -> None:
        from scripts.ai_flow.config import load_config, resolve_phase

        shown = agent_message(self.repo, "show economy profile")
        self.assertEqual(shown["action"], "profile_show")
        self.assertEqual(shown["profile"]["profile"], "custom")
        self.assertFalse(shown["routing"]["economy_configured"])
        self.assertEqual(shown["routing"]["phases"]["write"]["configured"]["provider"], "mock")
        self.assertIn("config profile apply economy", shown["reply"])
        shown_actions = {item["id"]: item for item in shown["actions"]}
        self.assertEqual(shown_actions["apply_economy_profile"]["kind"], "local_agent")
        self.assertEqual(shown_actions["apply_economy_profile"]["message"], "apply economy profile")
        self.assertTrue(shown_actions["apply_economy_profile"]["safe"])

        applied = agent_message(self.repo, "apply economy profile")

        self.assertEqual(applied["action"], "profile_apply")
        self.assertEqual(applied["profile"]["profile"], "economy")
        self.assertEqual(applied["profile"]["status"]["profile"], "economy")
        self.assertTrue(applied["routing"]["economy_configured"])
        self.assertFalse(applied["routing"]["economy_command_ready"])
        self.assertEqual(applied["routing"]["phases"]["write"]["configured"]["model"], "deepseek-v4-pro")
        self.assertEqual(applied["routing"]["phases"]["write"]["command_status"]["status"], "missing_config")
        self.assertIn("commands.reasonix", applied["reply"])
        applied_actions = {item["id"]: item for item in applied["actions"]}
        self.assertEqual(applied_actions["open_readiness"]["message"], "readiness")
        self.assertEqual(applied_actions["configure_reasonix_command"]["kind"], "local_agent")
        self.assertEqual(applied_actions["configure_reasonix_command"]["message"], "configure reasonix command")
        self.assertIn("commands.reasonix", applied_actions["configure_reasonix_command"]["command"])
        self.assertNotIn("start_new_task", applied_actions)
        cfg = load_config(self.repo)
        self.assertEqual(resolve_phase(cfg, "write")["model"], "deepseek-v4-pro")
        self.assertEqual(resolve_phase(cfg, "fix")["provider"], "reasonix_cli")
        self.assertFalse((self.repo / ".ai" / "runs").exists())

    def test_agent_routing_questions_show_profile_without_mutating_config(self) -> None:
        from scripts.ai_flow.config import load_config, resolve_phase

        for message in ("is writer using cheap model?", "what model will write and fix use?", "which provider handles implementation?", "can I use economy routing?"):
            with self.subTest(message=message):
                response = agent_message(self.repo, message)

                self.assertEqual(response["action"], "profile_show")
                self.assertIsNone(response["run_id"])
                self.assertFalse(response["routing"]["economy_configured"])
                self.assertIn("Economy routing profile is not active", response["reply"])

        cfg = load_config(self.repo)
        self.assertEqual(resolve_phase(cfg, "write")["provider"], "mock")
        self.assertEqual(resolve_phase(cfg, "fix")["provider"], "mock")
        self.assertFalse((self.repo / ".ai" / "runs").exists())

    def test_agent_routing_question_with_run_does_not_apply_patch_or_profile(self) -> None:
        from scripts.ai_flow.config import load_config, resolve_phase

        planned = agent_message(self.repo, "build routing question target")
        run_id = planned["run_id"]

        response = agent_message(self.repo, "is writer using cheap model?", run_id=run_id)

        self.assertEqual(response["action"], "profile_show")
        self.assertIsNone(response["run_id"])
        cfg = load_config(self.repo)
        self.assertEqual(resolve_phase(cfg, "write")["provider"], "mock")
        self.assertFalse((self.repo / ".ai" / "runs" / run_id / "APPROVAL.json").exists())

    def test_agent_applies_economy_profile_from_cost_effective_writer_instruction(self) -> None:
        from scripts.ai_flow.config import load_config, resolve_phase

        response = agent_message(self.repo, "像写手这样的大量简单工作让便宜的模型比如 DeepSeek 去干")

        self.assertEqual(response["action"], "profile_apply")
        self.assertIsNone(response["run_id"])
        self.assertTrue(response["routing"]["economy_configured"])
        self.assertEqual(response["routing"]["phases"]["write"]["configured"]["model"], "deepseek-v4-pro")
        cfg = load_config(self.repo)
        self.assertEqual(resolve_phase(cfg, "write")["provider"], "reasonix_cli")
        self.assertEqual(resolve_phase(cfg, "fix")["model"], "deepseek-v4-pro")
        self.assertFalse((self.repo / ".ai" / "runs").exists())

    def test_agent_can_configure_reasonix_command_without_starting_run(self) -> None:
        from scripts.ai_flow.config import load_config

        agent_message(self.repo, "apply economy profile")
        response = agent_message(self.repo, "configure reasonix command")

        self.assertEqual(response["action"], "reasonix_command_configure")
        self.assertTrue(response["ok"])
        self.assertIn("Reasonix command configured", response["reply"])
        self.assertEqual(response["config_update"]["set"]["commands.reasonix"], "reasonix")
        self.assertTrue(response["routing"]["economy_configured"])
        self.assertTrue(response["routing"]["phases"]["write"]["command_status"]["required"])
        self.assertEqual(response["routing"]["phases"]["write"]["command_status"]["command"], "reasonix")
        self.assertEqual(load_config(self.repo)["commands"]["reasonix"], "reasonix")
        self.assertFalse((self.repo / ".ai" / "runs").exists())

    def test_agent_can_configure_reasonix_command_from_chinese_prompt(self) -> None:
        from scripts.ai_flow.config import load_config

        agent_message(self.repo, "apply economy profile")
        response = agent_message(self.repo, "配置 Reasonix 命令")

        self.assertEqual(response["action"], "reasonix_command_configure")
        self.assertEqual(response["config_update"]["set"]["commands.reasonix"], "reasonix")
        self.assertEqual(response["reasonix_command"]["source"], "default")
        self.assertEqual(load_config(self.repo)["commands"]["reasonix"], "reasonix")
        self.assertFalse((self.repo / ".ai" / "runs").exists())

    def test_agent_can_configure_reasonix_command_from_chinese_use_prompt(self) -> None:
        from scripts.ai_flow.config import load_config

        response = agent_message(self.repo, "使用 Reasonix 命令")

        self.assertEqual(response["action"], "reasonix_command_configure")
        self.assertEqual(response["config_update"]["set"]["commands.reasonix"], "reasonix")
        self.assertEqual(load_config(self.repo)["commands"]["reasonix"], "reasonix")
        self.assertFalse((self.repo / ".ai" / "runs").exists())

    def test_agent_can_configure_reasonix_command_with_explicit_path(self) -> None:
        from scripts.ai_flow.config import load_config

        command_path = self.tempdir / "Reasonix CLI" / "reasonix.cmd"
        expected_command = f'"{command_path}"'
        agent_message(self.repo, "apply economy profile")
        response = agent_message(self.repo, f'configure reasonix command to "{command_path}"')

        self.assertEqual(response["action"], "reasonix_command_configure")
        self.assertEqual(response["config_update"]["set"]["commands.reasonix"], expected_command)
        self.assertEqual(response["reasonix_command"]["command"], expected_command)
        self.assertEqual(response["reasonix_command"]["source"], "message")
        self.assertEqual(load_config(self.repo)["commands"]["reasonix"], expected_command)
        self.assertEqual(response["routing"]["phases"]["write"]["command_status"]["command"], expected_command)
        self.assertEqual(response["routing"]["phases"]["write"]["command_status"]["executable"], str(command_path))
        self.assertFalse((self.repo / ".ai" / "runs").exists())

    def test_agent_can_configure_reasonix_command_from_chinese_path_prompt(self) -> None:
        from scripts.ai_flow.config import load_config

        command_path = self.tempdir / "Reasonix CLI" / "reasonix.cmd"
        expected_command = f'"{command_path}"'
        agent_message(self.repo, "apply economy profile")
        response = agent_message(self.repo, f'把 Reasonix 命令设为 "{command_path}"')

        self.assertEqual(response["action"], "reasonix_command_configure")
        self.assertEqual(response["config_update"]["set"]["commands.reasonix"], expected_command)
        self.assertEqual(response["reasonix_command"]["command"], expected_command)
        self.assertEqual(response["reasonix_command"]["source"], "message")
        self.assertEqual(load_config(self.repo)["commands"]["reasonix"], expected_command)
        self.assertEqual(response["routing"]["phases"]["write"]["command_status"]["command"], expected_command)
        self.assertEqual(response["routing"]["phases"]["write"]["command_status"]["executable"], str(command_path))
        self.assertFalse((self.repo / ".ai" / "runs").exists())

    def test_agent_doctor_word_in_task_still_starts_plan(self) -> None:
        response = agent_message(self.repo, "build doctor profile workflow")

        self.assertEqual(response["action"], "start")
        self.assertEqual(response["status"]["status"], "PLANNED")
        self.assertIsNotNone(response["run_id"])

        patchbay_task = agent_message(self.repo, "fix patchbay doctor bug")
        self.assertEqual(patchbay_task["action"], "start")
        self.assertEqual(patchbay_task["status"]["status"], "PLANNED")

        cost_dashboard_task = agent_message(self.repo, "optimize cost dashboard")
        self.assertEqual(cost_dashboard_task["action"], "start")
        self.assertEqual(cost_dashboard_task["status"]["status"], "PLANNED")

    def test_agent_reasonix_command_words_in_chinese_task_still_start_plan(self) -> None:
        response = agent_message(self.repo, "使用 Reasonix 命令修复 writer 流程")

        self.assertEqual(response["action"], "start")
        self.assertEqual(response["status"]["status"], "PLANNED")

    def test_agent_help_message_returns_capabilities_without_starting_run(self) -> None:
        response = agent_message(self.repo, "help")

        self.assertEqual(response["action"], "help")
        self.assertIsNone(response["run_id"])
        self.assertIn("capabilities", response)
        self.assertIn("setup", response["next_actions"])
        self.assertIn("readiness", response["next_actions"])
        setup_capability = next(item for item in response["capabilities"] if item["name"] == "setup")
        self.assertIn("Claude Desktop", setup_capability["summary"])
        self.assertIn("Gemini CLI", setup_capability["summary"])
        actions = {item["id"]: item for item in response["actions"]}
        self.assertEqual(actions["run_setup"]["kind"], "local_agent")
        self.assertEqual(actions["run_setup"]["message"], "patchbay setup")
        self.assertEqual(actions["start_new_task"]["kind"], "focus_composer")
        self.assertEqual(actions["open_readiness"]["message"], "readiness")
        self.assertEqual(actions["apply_economy_profile"]["message"], "apply economy profile")
        self.assertEqual(actions["configure_reasonix_command"]["message"], "configure reasonix command")
        self.assertIn("commands.reasonix", actions["configure_reasonix_command"]["command"])
        self.assertEqual(actions["show_runs"]["message"], "status")
        self.assertTrue(all(item["safe"] for item in actions.values()))
        self.assertFalse((self.repo / ".ai" / "runs").exists())

    def test_agent_chinese_help_prompts_return_help_without_starting_run(self) -> None:
        for message in ("Patchbay 怎么用", "如何使用 Patchbay", "使用说明", "新手引导"):
            with self.subTest(message=message):
                response = agent_message(self.repo, message)

                self.assertEqual(response["action"], "help")
                self.assertIsNone(response["run_id"])
                self.assertIn("capabilities", response)

        self.assertFalse((self.repo / ".ai" / "runs").exists())

    def test_agent_patchbay_setup_runs_local_setup_without_starting_run(self) -> None:
        codex_home = self.tempdir / "codex-home"

        with mock.patch.dict(os.environ, {"CODEX_HOME": str(codex_home)}):
            response = agent_message(self.repo, "patchbay setup")

        self.assertEqual(response["action"], "setup")
        self.assertTrue(response["ok"])
        self.assertIsNone(response["run_id"])
        self.assertIn("setup", response)
        self.assertTrue((codex_home / "skills" / "patchbay" / "SKILL.md").exists())
        runs_path = self.repo / ".ai" / "runs"
        self.assertFalse(runs_path.exists() and any(runs_path.iterdir()))

    def test_agent_chinese_setup_help_runs_local_setup_without_starting_run(self) -> None:
        import scripts.ai_flow.agent as agent_module

        calls: list[str] = []

        def fake_setup(root: Path, *, host: str = "codex", **_: object) -> dict[str, object]:
            calls.append(host)
            return {
                "ok": True,
                "root": str(root),
                "mcp": {"host": host, "command": f"patchbay mcp install {host}", "executed": False},
                "doctor": {"ok": True},
                "next_actions": ["readiness", "start"],
                "actions": [
                    {
                        "id": "open_readiness",
                        "label": "Open readiness",
                        "kind": "local_agent",
                        "message": "readiness",
                        "safe": True,
                        "reason": "Run read-only setup diagnostics.",
                    }
                ],
            }

        with mock.patch.object(agent_module, "run_setup", side_effect=fake_setup):
            default = agent_message(self.repo, "帮我配置 Patchbay")
            desktop = agent_message(self.repo, "帮助我配置 Patchbay 到 Claude 桌面")

        self.assertEqual(calls, ["codex", "claude-desktop"])
        self.assertEqual(default["action"], "setup")
        self.assertEqual(desktop["setup_host"], "claude-desktop")
        self.assertFalse((self.repo / ".ai" / "runs").exists())

    def test_agent_setup_message_can_target_mcp_host(self) -> None:
        import scripts.ai_flow.agent as agent_module

        calls: list[str] = []

        def fake_setup(root: Path, *, host: str = "codex", **_: object) -> dict[str, object]:
            calls.append(host)
            return {
                "ok": True,
                "root": str(root),
                "mcp": {"host": host, "command": f"patchbay mcp install {host}", "executed": False},
                "doctor": {"ok": True},
                "next_actions": [f"Register the MCP server with: patchbay mcp install {host}"],
                "actions": [
                    {
                        "id": "register_mcp",
                        "label": "Register MCP",
                        "kind": "command",
                        "command": f"patchbay mcp install {host}",
                        "safe": True,
                        "reason": "Register the MCP server command returned by setup.",
                    }
                ],
            }

        with mock.patch.object(agent_module, "run_setup", side_effect=fake_setup):
            default = agent_message(self.repo, "patchbay setup")
            desktop = agent_message(self.repo, "patchbay setup for Claude Desktop")
            gemini = agent_message(self.repo, "install patchbay for Gemini CLI")
            claude_code = agent_message(self.repo, "patchbay setup --host=Claude Code")
            codex_desktop = agent_message(self.repo, "patchbay setup to Codex Desktop")
            zh_desktop = agent_message(self.repo, "把 Patchbay 安装到 Claude 桌面")
            zh_gemini = agent_message(self.repo, "安装到 Gemini 命令行")
            codex_skill = agent_message(self.repo, "install Codex Skill")
            desktop_mcp = agent_message(self.repo, "register MCP for Claude Desktop")
            zh_codex_skill = agent_message(self.repo, "安装 Codex Skill")
            zh_gemini_mcp = agent_message(self.repo, "注册 MCP 到 Gemini 命令行")

        self.assertEqual(
            calls,
            [
                "codex",
                "claude-desktop",
                "gemini",
                "claude-code",
                "codex",
                "claude-desktop",
                "gemini",
                "codex",
                "claude-desktop",
                "codex",
                "gemini",
            ],
        )
        self.assertEqual(default["setup_host"], "codex")
        self.assertEqual(desktop["setup_host"], "claude-desktop")
        self.assertEqual(gemini["setup"]["mcp"]["host"], "gemini")
        self.assertEqual(claude_code["setup_host"], "claude-code")
        self.assertEqual(codex_desktop["setup_host"], "codex")
        self.assertEqual(zh_desktop["setup_host"], "claude-desktop")
        self.assertEqual(zh_gemini["setup_host"], "gemini")
        self.assertEqual(codex_skill["setup_host"], "codex")
        self.assertEqual(desktop_mcp["setup_host"], "claude-desktop")
        self.assertEqual(zh_codex_skill["setup_host"], "codex")
        self.assertEqual(zh_gemini_mcp["setup_host"], "gemini")
        desktop_actions = {item["id"]: item for item in desktop["actions"]}
        self.assertEqual(desktop_actions["register_mcp"]["kind"], "command")
        self.assertEqual(desktop_actions["register_mcp"]["command"], "patchbay mcp install claude-desktop")
        self.assertTrue(desktop_actions["register_mcp"]["safe"])
        self.assertFalse((self.repo / ".ai" / "runs").exists())

    def test_agent_setup_word_in_task_still_starts_plan(self) -> None:
        response = agent_message(self.repo, "setup auth flow")

        self.assertEqual(response["action"], "start")
        self.assertEqual(response["status"]["status"], "PLANNED")

    def test_agent_status_without_run_lists_recent_runs_without_planning(self) -> None:
        planned = agent_message(self.repo, "status summary target")

        response = agent_message(self.repo, "status")

        self.assertEqual(response["action"], "runs")
        self.assertIsNone(response["run_id"])
        self.assertEqual(response["recent_run"]["run_id"], planned["run_id"])
        self.assertEqual(response["runs"]["count"], 1)
        actions = {item["id"]: item for item in response["actions"]}
        self.assertEqual(actions["open_latest_run"]["kind"], "open_run")
        self.assertEqual(actions["open_latest_run"]["run_id"], planned["run_id"])
        self.assertTrue(actions["open_latest_run"]["safe"])
        self.assertEqual(actions["open_readiness"]["message"], "readiness")
        self.assertIn("open latest run", response["next_actions"])
        self.assertNotIn("continue", response["next_actions"])
        self.assertNotIn("approve", response["next_actions"])
        self.assertNotIn("apply", response["next_actions"])
        self.assertEqual(len(list((self.repo / ".ai" / "runs").iterdir())), 1)

    def test_agent_status_without_runs_returns_structured_start_actions(self) -> None:
        response = agent_message(self.repo, "status")

        self.assertEqual(response["action"], "runs")
        self.assertTrue(response["ok"])
        self.assertIsNone(response["run_id"])
        self.assertIsNone(response["recent_run"])
        self.assertEqual(response["runs"]["count"], 0)
        self.assertEqual(response["next_actions"], ["start", "readiness"])
        actions = {item["id"]: item for item in response["actions"]}
        self.assertEqual(actions["start_new_task"]["kind"], "focus_composer")
        self.assertTrue(actions["start_new_task"]["safe"])
        self.assertEqual(actions["open_readiness"]["message"], "readiness")
        self.assertNotIn("continue", response["next_actions"])
        self.assertNotIn("approve", response["next_actions"])
        self.assertNotIn("apply", response["next_actions"])
        self.assertEqual(len(list((self.repo / ".ai" / "runs").iterdir())), 0)

    def test_agent_next_step_without_run_points_to_latest_run_without_advancing(self) -> None:
        planned = agent_message(self.repo, "build handoff target for next-step testing")
        run_id = planned["run_id"]

        response = agent_message(self.repo, "what should I do next?")

        self.assertEqual(response["action"], "next_step")
        self.assertTrue(response["ok"])
        self.assertIsNone(response["run_id"])
        self.assertEqual(response["recent_run"]["run_id"], run_id)
        self.assertEqual(response["run_reference"]["run_id"], run_id)
        self.assertEqual(response["run_reference"]["status"], "PLANNED")
        self.assertEqual(response["run_reference"]["next_actions"], ["approve_and_run", "status", "events", "artifact"])
        self.assertEqual(response["latest_status"]["status"], "PLANNED")
        actions = {item["id"]: item for item in response["actions"]}
        self.assertEqual(actions["open_latest_run"]["kind"], "open_run")
        self.assertEqual(actions["open_latest_run"]["run_id"], run_id)
        self.assertEqual(actions["open_plan"]["tab"], "Artifacts")
        self.assertEqual(actions["open_readiness"]["message"], "readiness")
        self.assertIn("open latest run", response["next_actions"])
        self.assertIn("approve_and_run", response["next_actions"])
        self.assertFalse((self.repo / ".ai" / "runs" / run_id / "APPROVAL.json").exists())

    def test_agent_next_step_with_run_reports_gate_without_advancing(self) -> None:
        planned = agent_message(self.repo, "build selected flow for next-step testing")
        run_id = planned["run_id"]

        for message in ("next step", "现在该干什么", "下一步是什么"):
            with self.subTest(message=message):
                response = agent_message(self.repo, message, run_id=run_id)

                self.assertEqual(response["action"], "next_step")
                self.assertEqual(response["run_id"], run_id)
                self.assertEqual(response["status"]["status"], "PLANNED")
                self.assertEqual(response["requires_confirmation"]["confirmation"], "plan_approved")
                actions = {item["id"]: item for item in response["actions"]}
                self.assertEqual(actions["open_plan"]["tab"], "Artifacts")
                self.assertEqual(actions["open_trace"]["tab"], "Trace")
                self.assertFalse((self.repo / ".ai" / "runs" / run_id / "APPROVAL.json").exists())

    def test_agent_gate_status_explains_apply_blockers_without_advancing(self) -> None:
        planned = agent_message(self.repo, "build gate diagnosis target")
        run_id = planned["run_id"]

        response = agent_message(self.repo, "why can't I apply?", run_id=run_id)

        self.assertEqual(response["action"], "gate_status")
        self.assertEqual(response["run_id"], run_id)
        self.assertEqual(response["status"]["status"], "PLANNED")
        self.assertFalse(response["gate_diagnosis"]["ready_to_apply"])
        blocker_keys = [item["key"] for item in response["gate_diagnosis"]["blockers"]]
        self.assertIn("approval", blocker_keys)
        self.assertIn("tests", blocker_keys)
        self.assertIn("review", blocker_keys)
        self.assertIn("apply", blocker_keys)
        actions = {item["id"]: item for item in response["actions"]}
        self.assertEqual(actions["open_plan"]["tab"], "Artifacts")
        self.assertEqual(actions["open_trace"]["tab"], "Trace")
        self.assertEqual(actions["open_readiness"]["message"], "readiness")
        self.assertFalse((self.repo / ".ai" / "runs" / run_id / "APPROVAL.json").exists())

    def test_agent_gate_status_without_run_is_latest_run_handoff(self) -> None:
        planned = agent_message(self.repo, "build latest gate diagnosis")
        run_id = planned["run_id"]

        response = agent_message(self.repo, "what is blocking apply?")

        self.assertEqual(response["action"], "gate_status")
        self.assertIsNone(response["run_id"])
        self.assertEqual(response["recent_run"]["run_id"], run_id)
        self.assertEqual(response["run_reference"]["run_id"], run_id)
        self.assertEqual(response["run_reference"]["gate_diagnosis"]["status"], "PLANNED")
        self.assertEqual(response["latest_status"]["status"], "PLANNED")
        actions = {item["id"]: item for item in response["actions"]}
        self.assertEqual(actions["open_latest_run"]["kind"], "open_run")
        self.assertEqual(actions["open_latest_run"]["run_id"], run_id)
        self.assertNotIn("apply", response["next_actions"])
        self.assertFalse((self.repo / ".ai" / "runs" / run_id / "APPROVAL.json").exists())

    def test_agent_gate_status_reports_ready_apply_gate(self) -> None:
        planned = agent_message(self.repo, "build ready gate diagnosis")
        run_id = planned["run_id"]
        agent_message(self.repo, "approve", run_id=run_id, confirmation=PLAN_CONFIRMATION)

        response = agent_message(self.repo, "why is apply blocked", run_id=run_id)

        self.assertEqual(response["action"], "gate_status")
        self.assertTrue(response["gate_diagnosis"]["ready_to_apply"])
        self.assertEqual(response["gate_diagnosis"]["blockers"], [])
        self.assertEqual(response["requires_confirmation"]["confirmation"], APPLY_CONFIRMATION)
        actions = {item["id"]: item for item in response["actions"]}
        self.assertEqual(actions["open_diff"]["tab"], "Diff")

    def test_agent_chinese_runs_prompts_list_runs_without_planning(self) -> None:
        planned = agent_message(self.repo, "localized handoff target")

        for message in ("查看运行", "查看最近运行", "打开最近运行", "最近任务", "任务列表"):
            with self.subTest(message=message):
                response = agent_message(self.repo, message)

                self.assertEqual(response["action"], "runs")
                self.assertEqual(response["recent_run"]["run_id"], planned["run_id"])
                self.assertEqual(response["runs"]["count"], 1)
                actions = {item["id"]: item for item in response["actions"]}
                self.assertEqual(actions["open_latest_run"]["run_id"], planned["run_id"])

        self.assertEqual(len(list((self.repo / ".ai" / "runs").iterdir())), 1)

    def test_agent_status_word_in_task_still_starts_plan(self) -> None:
        response = agent_message(self.repo, "add status page")

        self.assertEqual(response["action"], "start")
        self.assertEqual(response["status"]["status"], "PLANNED")

    def test_agent_metrics_without_run_returns_local_guidance(self) -> None:
        response = agent_message(self.repo, "metrics")

        self.assertEqual(response["action"], "missing_run")
        self.assertFalse(response["ok"])
        self.assertIsNone(response["run_id"])
        self.assertIn("needs an existing run_id", response["reply"])
        self.assertEqual(len(list((self.repo / ".ai" / "runs").iterdir())), 0)

    def test_agent_metrics_with_run_returns_efficiency_digest(self) -> None:
        planned = agent_message(self.repo, "metrics target")

        response = agent_message(self.repo, "metrics", run_id=planned["run_id"])

        self.assertEqual(response["action"], "metrics")
        self.assertTrue(response["ok"])
        self.assertEqual(response["run_id"], planned["run_id"])
        self.assertEqual(response["metrics"]["run_id"], planned["run_id"])
        self.assertIn("run_metrics", response["metrics"])
        self.assertIn("phase attempt", response["reply"])

    def test_agent_metrics_word_in_task_still_starts_plan(self) -> None:
        response = agent_message(self.repo, "improve metrics dashboard")

        self.assertEqual(response["action"], "start")
        self.assertEqual(response["status"]["status"], "PLANNED")

    def test_agent_status_returns_structured_failed_recovery(self) -> None:
        from scripts.ai_flow.state import mark_failed

        planned = agent_message(self.repo, "failed recovery target")
        run_path = self.repo / ".ai" / "runs" / planned["run_id"]
        (run_path / "writer.log").write_text("writer exploded\n", encoding="utf-8")
        mark_failed(
            run_path,
            error="writer exploded",
            stage="write",
            suggested_next_action="Inspect writer.log and rerun with a narrower task.",
        )

        response = agent_message(self.repo, "status", run_id=planned["run_id"])

        self.assertEqual(response["status"]["status"], "FAILED")
        self.assertIn("recovery", response)
        self.assertEqual(response["recovery"]["stage"], "write")
        self.assertIn("writer.log", response["recovery"]["artifacts"])
        recovery_actions = {item["id"]: item for item in response["recovery"]["actions"]}
        self.assertEqual(recovery_actions["inspect_events"]["kind"], "diagnostic_tab")
        self.assertEqual(recovery_actions["inspect_artifacts"]["tab"], "Artifacts")
        self.assertEqual(recovery_actions["start_new_task"]["kind"], "focus_composer")
        self.assertIn("Inspect writer.log", response["reply"])
        self.assertEqual(response["next_actions"], ["status", "events", "artifact", "diff"])

    def test_agent_continue_without_run_returns_local_guidance(self) -> None:
        response = agent_message(self.repo, "continue")

        self.assertEqual(response["action"], "missing_run")
        self.assertFalse(response["ok"])
        self.assertIsNone(response["run_id"])
        self.assertIn("needs an existing run_id", response["reply"])
        self.assertIsNone(response["recent_run"])
        self.assertIsNone(response["run_reference"])
        self.assertEqual(response["next_actions"], ["start", "readiness"])
        actions = {item["id"]: item for item in response["actions"]}
        self.assertEqual(actions["start_new_task"]["kind"], "focus_composer")
        self.assertTrue(actions["start_new_task"]["safe"])
        self.assertEqual(actions["open_readiness"]["message"], "readiness")
        self.assertEqual(len(list((self.repo / ".ai" / "runs").iterdir())), 0)

    def test_agent_apply_without_run_returns_local_guidance(self) -> None:
        response = agent_message(self.repo, "apply")

        self.assertEqual(response["action"], "missing_run")
        self.assertFalse(response["ok"])
        self.assertIsNone(response["run_id"])
        self.assertIn("needs an existing run_id", response["reply"])

    def test_agent_continue_without_run_points_to_latest_run_without_advancing(self) -> None:
        planned = agent_message(self.repo, "latest handoff target")
        run_id = planned["run_id"]

        response = agent_message(self.repo, "continue")

        self.assertEqual(response["action"], "missing_run")
        self.assertFalse(response["ok"])
        self.assertIsNone(response["run_id"])
        self.assertEqual(response["recent_run"]["run_id"], run_id)
        self.assertEqual(response["run_reference"]["run_id"], run_id)
        self.assertEqual(response["run_reference"]["status"], "PLANNED")
        self.assertEqual(response["run_reference"]["safe_actions"], ["open_run", "status", "events"])
        actions = {item["id"]: item for item in response["actions"]}
        self.assertEqual(actions["open_latest_run"]["kind"], "open_run")
        self.assertEqual(actions["open_latest_run"]["run_id"], run_id)
        self.assertTrue(actions["open_latest_run"]["safe"])
        self.assertEqual(actions["show_runs"]["message"], "status")
        self.assertEqual(actions["open_readiness"]["message"], "readiness")
        self.assertIn("open latest run", response["next_actions"])
        self.assertNotIn("continue", response["next_actions"])
        self.assertNotIn("approve", response["next_actions"])
        self.assertNotIn("apply", response["next_actions"])
        self.assertFalse((self.repo / ".ai" / "runs" / run_id / "APPROVAL.json").exists())

    def test_agent_approve_without_run_points_to_latest_run_without_confirming(self) -> None:
        planned = agent_message(self.repo, "latest approval handoff")
        run_id = planned["run_id"]

        response = agent_message(self.repo, "approve")

        self.assertEqual(response["action"], "missing_run")
        self.assertEqual(response["recent_run"]["run_id"], run_id)
        self.assertEqual(response["run_reference"]["run_id"], run_id)
        self.assertIn("open latest run", response["next_actions"])
        self.assertFalse((self.repo / ".ai" / "runs" / run_id / "APPROVAL.json").exists())

    def test_agent_missing_run_preserves_requested_view(self) -> None:
        agent_message(self.repo, "latest view handoff")

        self.assertEqual(agent_message(self.repo, "diff")["run_reference"]["requested_view"]["tab"], "Diff")
        self.assertEqual(agent_message(self.repo, "events")["run_reference"]["requested_view"]["tab"], "Trace")
        self.assertEqual(agent_message(self.repo, "logs")["run_reference"]["requested_view"]["tab"], "Log")
        self.assertEqual(agent_message(self.repo, "artifact")["run_reference"]["requested_view"]["tab"], "Artifacts")
        self.assertEqual(agent_message(self.repo, "看补丁")["run_reference"]["requested_view"]["tab"], "Diff")
        self.assertEqual(agent_message(self.repo, "查看事件轨迹")["run_reference"]["requested_view"]["tab"], "Trace")
        self.assertEqual(agent_message(self.repo, "打开日志")["run_reference"]["requested_view"]["tab"], "Log")
        self.assertEqual(agent_message(self.repo, "看计划产物")["run_reference"]["requested_view"]["tab"], "Artifacts")
        self.assertEqual(agent_message(self.repo, "查看失败原因")["run_reference"]["requested_view"]["tab"], "Log")
        self.assertEqual(agent_message(self.repo, "为什么失败")["run_reference"]["requested_view"]["tab"], "Log")
        self.assertEqual(agent_message(self.repo, "why did it fail")["run_reference"]["requested_view"]["tab"], "Log")

    def test_agent_run_bound_view_prompts_return_diagnostic_actions(self) -> None:
        planned = agent_message(self.repo, "selected run diagnostics")
        run_id = planned["run_id"]

        cases = [
            ("diff", "Diff", "diff"),
            ("events", "Trace", "status"),
            ("查看失败原因", "Log", "artifact"),
            ("查看计划产物", "Artifacts", "artifact"),
        ]
        for message, tab, expected_action in cases:
            with self.subTest(message=message):
                response = agent_message(self.repo, message, run_id=run_id)

                self.assertEqual(response["action"], expected_action)
                self.assertEqual(response["requested_view"]["tab"], tab)
                self.assertEqual(response["actions"][0]["kind"], "diagnostic_tab")
                self.assertEqual(response["actions"][0]["tab"], tab)
                self.assertTrue(response["actions"][0]["safe"])
                self.assertFalse((self.repo / ".ai" / "runs" / run_id / "APPROVAL.json").exists())

        self.assertEqual(len(list((self.repo / ".ai" / "runs").iterdir())), 1)

    def test_agent_chinese_gate_phrases_without_run_point_to_latest_run(self) -> None:
        planned = agent_message(self.repo, "latest chinese gate handoff")
        run_id = planned["run_id"]

        for message in ("继续推进", "确认计划", "应用补丁", "查看成本"):
            with self.subTest(message=message):
                response = agent_message(self.repo, message)
                self.assertEqual(response["action"], "missing_run")
                self.assertEqual(response["recent_run"]["run_id"], run_id)
                self.assertEqual(response["run_reference"]["run_id"], run_id)
                self.assertIn("open latest run", response["next_actions"])

        self.assertEqual(len(list((self.repo / ".ai" / "runs").iterdir())), 1)

    def test_agent_review_code_remains_a_new_task(self) -> None:
        response = agent_message(self.repo, "review code quality")

        self.assertEqual(response["action"], "start")
        self.assertEqual(response["status"]["status"], "PLANNED")

        approval_task = agent_message(self.repo, "approve user permissions flow")
        self.assertEqual(approval_task["action"], "start")
        self.assertEqual(approval_task["status"]["status"], "PLANNED")

    def test_agent_chinese_task_phrases_with_gate_words_still_start_plan(self) -> None:
        plan_page = agent_message(self.repo, "实现确认计划页面")
        patch_button = agent_message(self.repo, "修复应用补丁按钮")

        self.assertEqual(plan_page["action"], "start")
        self.assertEqual(patch_button["action"], "start")
        self.assertIsNotNone(plan_page["run_id"])
        self.assertIsNotNone(patch_button["run_id"])

    def test_agent_refuses_approval_without_confirmation(self) -> None:
        planned = agent_message(self.repo, "needs approval")
        run_id = planned["run_id"]

        response = agent_message(self.repo, "approve", run_id=run_id)

        self.assertEqual(response["status"]["status"], "PLANNED")
        self.assertEqual(response["requires_confirmation"]["confirmation"], PLAN_CONFIRMATION)
        self.assertFalse((self.repo / ".ai" / "runs" / run_id / "APPROVAL.json").exists())

    def test_agent_approve_and_run_reaches_apply_gate(self) -> None:
        planned = agent_message(self.repo, "ready for agent autopilot")

        response = agent_message(self.repo, "approve", run_id=planned["run_id"], confirmation=PLAN_CONFIRMATION)

        self.assertTrue(response["ok"])
        self.assertEqual(response["status"]["status"], "REVIEWED_PASS")
        self.assertTrue(response["status"]["gate_state"]["ready_to_apply"])
        self.assertEqual(response["requires_confirmation"]["confirmation"], APPLY_CONFIRMATION)
        self.assertIn("PATCHBAY_MOCK_OUTPUT.md", response["diff"])

    def test_agent_apply_requires_confirmation(self) -> None:
        planned = agent_message(self.repo, "apply confirmation")
        run_id = planned["run_id"]
        agent_message(self.repo, "approve", run_id=run_id, confirmation=PLAN_CONFIRMATION)

        refused = agent_message(self.repo, "apply", run_id=run_id)
        self.assertEqual(refused["requires_confirmation"]["confirmation"], APPLY_CONFIRMATION)
        self.assertFalse((self.repo / "PATCHBAY_MOCK_OUTPUT.md").exists())

        applied = agent_message(self.repo, "apply", run_id=run_id, confirmation=APPLY_CONFIRMATION)
        self.assertEqual(applied["status"]["status"], "APPLIED")
        self.assertTrue((self.repo / "PATCHBAY_MOCK_OUTPUT.md").exists())

    def test_agent_apply_does_not_ask_for_confirmation_before_gate_is_ready(self) -> None:
        planned = agent_message(self.repo, "not ready for apply")

        response = agent_message(self.repo, "apply", run_id=planned["run_id"])

        self.assertFalse(response["ok"])
        self.assertEqual(response["status"]["status"], "PLANNED")
        self.assertNotEqual(response["requires_confirmation"]["confirmation"], APPLY_CONFIRMATION)
        self.assertIn("Apply is blocked", response["reply"])

    def test_agent_does_not_apply_when_tests_are_skipped_by_default(self) -> None:
        self._write_mock_config(allow_without_tests=False)
        planned = agent_message(self.repo, "skip tests stays blocked")

        response = agent_message(self.repo, "approve", run_id=planned["run_id"], confirmation=PLAN_CONFIRMATION)

        self.assertTrue(response["ok"])
        self.assertEqual(response["status"]["status"], "REVIEWED_PASS")
        self.assertFalse(response["status"]["gate_state"]["ready_to_apply"])
        self.assertEqual(response["status"]["gate_state"]["tests_status"], "SKIPPED")
        self.assertIsNone(response["requires_confirmation"])

        apply_response = agent_message(self.repo, "apply", run_id=planned["run_id"])
        self.assertFalse(apply_response["ok"])
        self.assertIsNone(apply_response["requires_confirmation"])

    def test_mcp_patchbay_agent_wraps_same_service(self) -> None:
        from scripts.ai_flow import mcp_server

        original_root = mcp_server.ROOT
        try:
            mcp_server.ROOT = self.repo
            response = mcp_server.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": "patchbay_agent", "arguments": {"message": "mcp agent task"}},
                }
            )
        finally:
            mcp_server.ROOT = original_root

        payload = json.loads(response["result"]["content"][0]["text"])
        self.assertEqual(payload["status"]["status"], "PLANNED")
        self.assertEqual(payload["requires_confirmation"]["confirmation"], PLAN_CONFIRMATION)

    def test_mcp_patchbay_agent_can_run_doctor(self) -> None:
        from scripts.ai_flow import mcp_server

        original_root = mcp_server.ROOT
        try:
            mcp_server.ROOT = self.repo
            response = mcp_server.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": "patchbay_agent", "arguments": {"message": "readiness"}},
                }
            )
        finally:
            mcp_server.ROOT = original_root

        payload = json.loads(response["result"]["content"][0]["text"])
        self.assertEqual(payload["action"], "doctor")
        self.assertIn("checks", payload["doctor"])

    def test_mcp_patchbay_agent_can_apply_economy_profile(self) -> None:
        from scripts.ai_flow import mcp_server

        original_root = mcp_server.ROOT
        try:
            mcp_server.ROOT = self.repo
            response = mcp_server.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": "patchbay_agent", "arguments": {"message": "patchbay config profile apply economy"}},
                }
            )
        finally:
            mcp_server.ROOT = original_root

        payload = json.loads(response["result"]["content"][0]["text"])
        self.assertEqual(payload["action"], "profile_apply")
        self.assertEqual(payload["profile"]["status"]["profile"], "economy")

    def test_mcp_patchbay_agent_can_configure_reasonix_command(self) -> None:
        from scripts.ai_flow import mcp_server
        from scripts.ai_flow.config import load_config

        original_root = mcp_server.ROOT
        try:
            mcp_server.ROOT = self.repo
            response = mcp_server.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": "patchbay_agent", "arguments": {"message": "configure reasonix command"}},
                }
            )
        finally:
            mcp_server.ROOT = original_root

        payload = json.loads(response["result"]["content"][0]["text"])
        self.assertEqual(payload["action"], "reasonix_command_configure")
        self.assertEqual(payload["config_update"]["set"]["commands.reasonix"], "reasonix")
        self.assertEqual(load_config(self.repo)["commands"]["reasonix"], "reasonix")

    def test_mcp_patchbay_agent_can_configure_reasonix_command_from_chinese_prompt(self) -> None:
        from scripts.ai_flow import mcp_server
        from scripts.ai_flow.config import load_config

        original_root = mcp_server.ROOT
        try:
            mcp_server.ROOT = self.repo
            response = mcp_server.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": "patchbay_agent", "arguments": {"message": "配置 Reasonix 命令"}},
                }
            )
        finally:
            mcp_server.ROOT = original_root

        payload = json.loads(response["result"]["content"][0]["text"])
        self.assertEqual(payload["action"], "reasonix_command_configure")
        self.assertEqual(payload["config_update"]["set"]["commands.reasonix"], "reasonix")
        self.assertEqual(load_config(self.repo)["commands"]["reasonix"], "reasonix")

    def test_mcp_patchbay_agent_can_run_setup_without_starting_run(self) -> None:
        from scripts.ai_flow import mcp_server

        codex_home = self.tempdir / "mcp-codex-home"
        original_root = mcp_server.ROOT
        try:
            mcp_server.ROOT = self.repo
            with mock.patch.dict(os.environ, {"CODEX_HOME": str(codex_home)}):
                response = mcp_server.handle(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {"name": "patchbay_agent", "arguments": {"message": "install patchbay"}},
                    }
                )
        finally:
            mcp_server.ROOT = original_root

        payload = json.loads(response["result"]["content"][0]["text"])
        self.assertEqual(payload["action"], "setup")
        self.assertTrue(payload["ok"])
        self.assertIsNone(payload["run_id"])
        self.assertTrue((codex_home / "skills" / "patchbay" / "SKILL.md").exists())
        runs_path = self.repo / ".ai" / "runs"
        self.assertFalse(runs_path.exists() and any(runs_path.iterdir()))

    def test_mcp_patchbay_agent_setup_can_target_host(self) -> None:
        from scripts.ai_flow import mcp_server
        import scripts.ai_flow.agent as agent_module

        original_root = mcp_server.ROOT
        try:
            mcp_server.ROOT = self.repo
            with mock.patch.object(
                agent_module,
                "run_setup",
                return_value={
                    "ok": True,
                    "mcp": {"host": "claude-code", "command": "patchbay mcp install claude-code", "executed": False},
                    "doctor": {"ok": True},
                    "next_actions": ["Register the MCP server with: patchbay mcp install claude-code"],
                    "actions": [
                        {
                            "id": "register_mcp",
                            "label": "Register MCP",
                            "kind": "command",
                            "command": "patchbay mcp install claude-code",
                            "safe": True,
                            "reason": "Register the MCP server command returned by setup.",
                        }
                    ],
                },
            ) as setup_mock:
                response = mcp_server.handle(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {"name": "patchbay_agent", "arguments": {"message": "install patchbay for claude code"}},
                    }
                )
        finally:
            mcp_server.ROOT = original_root

        payload = json.loads(response["result"]["content"][0]["text"])
        self.assertEqual(payload["action"], "setup")
        self.assertEqual(payload["setup_host"], "claude-code")
        self.assertEqual(setup_mock.call_args.kwargs["host"], "claude-code")
        self.assertIsNone(payload["run_id"])
        actions = {item["id"]: item for item in payload["actions"]}
        self.assertEqual(actions["register_mcp"]["kind"], "command")
        self.assertEqual(actions["register_mcp"]["command"], "patchbay mcp install claude-code")

    def test_mcp_patchbay_agent_can_list_runs_without_run_id(self) -> None:
        from scripts.ai_flow import mcp_server

        planned = agent_message(self.repo, "mcp planning target")
        original_root = mcp_server.ROOT
        try:
            mcp_server.ROOT = self.repo
            response = mcp_server.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": "patchbay_agent", "arguments": {"message": "status"}},
                }
            )
        finally:
            mcp_server.ROOT = original_root

        payload = json.loads(response["result"]["content"][0]["text"])
        self.assertEqual(payload["action"], "runs")
        self.assertEqual(payload["recent_run"]["run_id"], planned["run_id"])
        actions = {item["id"]: item for item in payload["actions"]}
        self.assertEqual(actions["open_latest_run"]["run_id"], planned["run_id"])
        self.assertTrue(actions["open_latest_run"]["safe"])
        self.assertNotIn("continue", payload["next_actions"])

    def test_mcp_patchbay_agent_next_step_is_safe_handoff_without_run_id(self) -> None:
        from scripts.ai_flow import mcp_server

        planned = agent_message(self.repo, "build mcp next-step target")
        original_root = mcp_server.ROOT
        try:
            mcp_server.ROOT = self.repo
            response = mcp_server.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": "patchbay_agent", "arguments": {"message": "what should I do next"}},
                }
            )
        finally:
            mcp_server.ROOT = original_root

        payload = json.loads(response["result"]["content"][0]["text"])
        self.assertEqual(payload["action"], "next_step")
        self.assertIsNone(payload["run_id"])
        self.assertEqual(payload["recent_run"]["run_id"], planned["run_id"])
        self.assertEqual(payload["run_reference"]["next_actions"], ["approve_and_run", "status", "events", "artifact"])
        actions = {item["id"]: item for item in payload["actions"]}
        self.assertEqual(actions["open_latest_run"]["kind"], "open_run")
        self.assertEqual(actions["open_latest_run"]["run_id"], planned["run_id"])
        self.assertNotIn("approve", payload["next_actions"])
        self.assertFalse((self.repo / ".ai" / "runs" / planned["run_id"] / "APPROVAL.json").exists())

    def test_mcp_patchbay_agent_gate_status_is_read_only_handoff(self) -> None:
        from scripts.ai_flow import mcp_server

        planned = agent_message(self.repo, "build mcp gate target")
        original_root = mcp_server.ROOT
        try:
            mcp_server.ROOT = self.repo
            response = mcp_server.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": "patchbay_agent", "arguments": {"message": "what is blocking apply"}},
                }
            )
        finally:
            mcp_server.ROOT = original_root

        payload = json.loads(response["result"]["content"][0]["text"])
        self.assertEqual(payload["action"], "gate_status")
        self.assertIsNone(payload["run_id"])
        self.assertEqual(payload["recent_run"]["run_id"], planned["run_id"])
        self.assertFalse(payload["gate_diagnosis"]["ready_to_apply"])
        self.assertNotIn("apply", payload["next_actions"])
        self.assertFalse((self.repo / ".ai" / "runs" / planned["run_id"] / "APPROVAL.json").exists())

    def test_mcp_patchbay_agent_can_return_metrics_for_run(self) -> None:
        from scripts.ai_flow import mcp_server

        planned = agent_message(self.repo, "mcp metrics target")
        original_root = mcp_server.ROOT
        try:
            mcp_server.ROOT = self.repo
            response = mcp_server.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": "patchbay_agent", "arguments": {"message": "cost", "run_id": planned["run_id"]}},
                }
            )
        finally:
            mcp_server.ROOT = original_root

        payload = json.loads(response["result"]["content"][0]["text"])
        self.assertEqual(payload["action"], "metrics")
        self.assertEqual(payload["metrics"]["run_id"], planned["run_id"])
        self.assertIn("run_metrics", payload["metrics"])
        self.assertIn("routing_evidence", payload["metrics"])

    def test_agent_metrics_reports_economy_routing_evidence(self) -> None:
        from scripts.ai_flow.events import append_event

        agent_message(self.repo, "apply economy profile")
        self._set_reasonix_command_to_python()
        planned = agent_message(self.repo, "routing metrics target")
        run_path = self.repo / ".ai" / "runs" / planned["run_id"]
        append_event(
            run_path,
            phase="write",
            provider="reasonix_cli",
            model="deepseek-v4-pro",
            action="success",
            status="IMPLEMENTED",
            detail="synthetic economy writer event",
            duration_ms=1200,
        )

        response = agent_message(self.repo, "cost", run_id=planned["run_id"])

        routing = response["metrics"]["routing_evidence"]
        self.assertTrue(routing["economy_configured"])
        self.assertTrue(routing["economy_command_ready"])
        self.assertEqual(routing["command_not_ready_phases"], [])
        self.assertEqual(routing["observed_economy_phases"], ["write"])
        self.assertEqual(routing["coverage"]["observed_economy_total"], 1)
        self.assertEqual(routing["coverage"]["observed_economy_percent"], 50)
        self.assertEqual(routing["coverage"]["label"], "1/2 economy phases observed")
        self.assertEqual(routing["economy_health"]["status"], "pending_evidence")
        self.assertEqual(routing["economy_health"]["severity"], "info")
        self.assertEqual(routing["economy_health"]["missing_evidence"], ["fix"])
        self.assertEqual(routing["actions"][0]["id"], "wait_for_routing_evidence")
        self.assertEqual(response["actions"][0]["kind"], "diagnostic_tab")
        self.assertIn("fix", routing["missing_evidence"])
        self.assertEqual(routing["phases"]["write"]["observed"][0]["provider"], "reasonix_cli")
        self.assertIn("1/2 economy phases observed", routing["summary"])
        self.assertIn("economy health pending_evidence", response["reply"])
        self.assertIn("observed write", response["reply"])

    def test_agent_metrics_warns_when_economy_command_is_missing(self) -> None:
        agent_message(self.repo, "apply economy profile")
        planned = agent_message(self.repo, "routing command health target")

        response = agent_message(self.repo, "cost", run_id=planned["run_id"])

        routing = response["metrics"]["routing_evidence"]
        self.assertTrue(routing["economy_configured"])
        self.assertFalse(routing["economy_command_ready"])
        self.assertEqual(routing["command_not_ready_phases"], ["write", "fix"])
        self.assertEqual(routing["phases"]["write"]["command_status"]["status"], "missing_config")
        self.assertEqual(routing["phases"]["fix"]["command_status"]["status"], "missing_config")
        self.assertEqual(routing["economy_health"]["status"], "command_not_ready")
        self.assertEqual(routing["economy_health"]["next_action"], "configure_reasonix_command")
        self.assertEqual(routing["economy_health"]["command_not_ready_phases"], ["write", "fix"])
        self.assertEqual(routing["actions"][0]["id"], "configure_reasonix_command")
        self.assertEqual(response["actions"][0]["kind"], "local_agent")
        self.assertEqual(response["actions"][0]["message"], "configure reasonix command")
        self.assertIn("commands.reasonix", response["actions"][0]["command"])
        self.assertIn("economy health command_not_ready", response["reply"])

    def test_agent_metrics_flags_non_economy_provider_observed_on_economy_route(self) -> None:
        from scripts.ai_flow.events import append_event

        agent_message(self.repo, "apply economy profile")
        self._set_reasonix_command_to_python()
        planned = agent_message(self.repo, "routing drift target")
        run_path = self.repo / ".ai" / "runs" / planned["run_id"]
        append_event(
            run_path,
            phase="write",
            provider="mock",
            model="mock-model",
            action="success",
            status="IMPLEMENTED",
            detail="synthetic non-economy writer event",
            duration_ms=1200,
        )

        response = agent_message(self.repo, "cost", run_id=planned["run_id"])

        routing = response["metrics"]["routing_evidence"]
        self.assertTrue(routing["economy_configured"])
        self.assertEqual(routing["observed_non_economy_phases"], ["write"])
        self.assertEqual(routing["coverage"]["observed_other_total"], 1)
        self.assertEqual(routing["coverage"]["observed_economy_percent"], 0)
        self.assertEqual(routing["economy_health"]["status"], "drift")
        self.assertEqual(routing["economy_health"]["drift_phases"], ["write"])
        self.assertEqual(routing["actions"][0]["id"], "inspect_routing_events")
        self.assertEqual(response["actions"][0]["tab"], "Trace")
        self.assertIn("write observed a non-economy provider", routing["summary"])

    def test_agent_metrics_flags_mixed_provider_drift_on_economy_route(self) -> None:
        from scripts.ai_flow.events import append_event

        agent_message(self.repo, "apply economy profile")
        self._set_reasonix_command_to_python()
        planned = agent_message(self.repo, "mixed routing drift target")
        run_path = self.repo / ".ai" / "runs" / planned["run_id"]
        append_event(
            run_path,
            phase="write",
            provider="reasonix_cli",
            model="deepseek-v4-pro",
            action="success",
            status="IMPLEMENTED",
            detail="synthetic economy writer event",
            duration_ms=1200,
        )
        append_event(
            run_path,
            phase="write",
            provider="codex_cli",
            model="gpt-5.5",
            action="retry",
            status="IMPLEMENTED",
            detail="synthetic higher-cost writer retry",
            duration_ms=800,
        )

        response = agent_message(self.repo, "cost", run_id=planned["run_id"])

        routing = response["metrics"]["routing_evidence"]
        self.assertEqual(routing["phases"]["write"]["status"], "observed_mixed")
        self.assertEqual(routing["observed_economy_phases"], ["write"])
        self.assertEqual(routing["observed_non_economy_phases"], ["write"])
        self.assertEqual(routing["economy_health"]["status"], "drift")
        self.assertEqual(routing["coverage"]["observed_economy_percent"], 50)
        self.assertIn("non-economy provider", routing["summary"])

    def test_mcp_patchbay_agent_continue_without_run_returns_guidance(self) -> None:
        from scripts.ai_flow import mcp_server

        original_root = mcp_server.ROOT
        try:
            mcp_server.ROOT = self.repo
            response = mcp_server.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": "patchbay_agent", "arguments": {"message": "continue"}},
                }
            )
        finally:
            mcp_server.ROOT = original_root

        payload = json.loads(response["result"]["content"][0]["text"])
        self.assertEqual(payload["action"], "missing_run")
        self.assertFalse(payload["ok"])
        self.assertIsNone(payload["run_reference"])

    def test_cli_agent_message(self) -> None:
        response = self.cli_json("agent", "message", "cli agent task", "--include-plan")

        self.assertEqual(response["status"]["status"], "PLANNED")
        self.assertIn("PLAN.md", response["artifacts"])

    def test_cli_agent_doctor_message(self) -> None:
        response = self.cli_json("agent", "message", "readiness")

        self.assertEqual(response["action"], "doctor")
        self.assertIn("checks", response["doctor"])
        self.assertIsNone(response["run_id"])

    def test_cli_agent_apply_economy_profile_message(self) -> None:
        response = self.cli_json("agent", "message", "use economy routing")

        self.assertEqual(response["action"], "profile_apply")
        self.assertEqual(response["profile"]["status"]["profile"], "economy")
        self.assertIsNone(response["run_id"])

    def test_cli_agent_configure_reasonix_command_message(self) -> None:
        from scripts.ai_flow.config import load_config

        response = self.cli_json("agent", "message", "configure reasonix command")

        self.assertEqual(response["action"], "reasonix_command_configure")
        self.assertEqual(response["config_update"]["set"]["commands.reasonix"], "reasonix")
        self.assertEqual(load_config(self.repo)["commands"]["reasonix"], "reasonix")
        self.assertIsNone(response["run_id"])

    def test_cli_agent_configure_reasonix_command_accepts_explicit_path(self) -> None:
        from scripts.ai_flow.config import load_config

        command_path = self.tempdir / "Reasonix CLI" / "reasonix.cmd"
        expected_command = f'"{command_path}"'
        response = self.cli_json("agent", "message", f'configure reasonix command to "{command_path}"')

        self.assertEqual(response["action"], "reasonix_command_configure")
        self.assertEqual(response["config_update"]["set"]["commands.reasonix"], expected_command)
        self.assertEqual(response["reasonix_command"]["source"], "message")
        self.assertEqual(load_config(self.repo)["commands"]["reasonix"], expected_command)
        self.assertIsNone(response["run_id"])

    def test_cli_agent_patchbay_setup_runs_setup_without_starting_run(self) -> None:
        codex_home = self.tempdir / "cli-codex-home"

        response = self.cli_json("agent", "message", "patchbay setup", env={"CODEX_HOME": str(codex_home)})

        self.assertEqual(response["action"], "setup")
        self.assertTrue(response["ok"])
        self.assertIsNone(response["run_id"])
        self.assertIn("setup", response)
        self.assertTrue((codex_home / "skills" / "patchbay" / "SKILL.md").exists())
        self.assertIn("actions", response)
        self.assertIsInstance(response["actions"], list)
        runs_path = self.repo / ".ai" / "runs"
        self.assertFalse(runs_path.exists() and any(runs_path.iterdir()))

    def test_cli_agent_status_without_run_lists_runs(self) -> None:
        planned = agent_message(self.repo, "cli status target")

        response = self.cli_json("agent", "message", "status")

        self.assertEqual(response["action"], "runs")
        self.assertEqual(response["recent_run"]["run_id"], planned["run_id"])
        self.assertIsNone(response["run_id"])
        actions = {item["id"]: item for item in response["actions"]}
        self.assertEqual(actions["open_latest_run"]["run_id"], planned["run_id"])
        self.assertNotIn("continue", response["next_actions"])

    def test_cli_agent_metrics_with_run_returns_efficiency_digest(self) -> None:
        planned = agent_message(self.repo, "cli metrics target")

        response = self.cli_json("agent", "message", "tokens", "--run-id", planned["run_id"])

        self.assertEqual(response["action"], "metrics")
        self.assertEqual(response["metrics"]["run_id"], planned["run_id"])
        self.assertIn("run_metrics", response["metrics"])

    def test_cli_agent_continue_without_run_returns_local_guidance(self) -> None:
        response = self.cli_json("agent", "message", "continue")

        self.assertEqual(response["action"], "missing_run")
        self.assertFalse(response["ok"])
        self.assertIsNone(response["run_id"])
        self.assertIsNone(response["run_reference"])

    def test_agent_background_start_returns_pollable_job(self) -> None:
        response = agent_message(self.repo, "background agent plan", background=True)
        run_id = response["run_id"]
        run_path = self.repo / ".ai" / "runs" / run_id

        self.assertTrue(response["ok"])
        self.assertTrue(response["background"])
        self.assertEqual(response["job"]["phase"], "plan")
        self.assertEqual(response["next_actions"], ["status", "events"])
        self.assertTrue((run_path / "JOB.json").exists())
        self.assertTrue((run_path / "events.jsonl").exists())

    def test_agent_background_approval_requires_confirmation(self) -> None:
        planned = agent_message(self.repo, "background approval still gated")

        response = agent_message(self.repo, "approve", run_id=planned["run_id"], background=True)

        self.assertEqual(response["status"]["status"], "PLANNED")
        self.assertEqual(response["requires_confirmation"]["confirmation"], PLAN_CONFIRMATION)
        self.assertFalse((self.repo / ".ai" / "runs" / planned["run_id"] / "AGENT.lock").exists())

    def test_agent_background_continue_starts_agent_job(self) -> None:
        from scripts.ai_flow import agent as agent_module

        planned = agent_message(self.repo, "background autopilot")
        run_id = planned["run_id"]
        run_path = self.repo / ".ai" / "runs" / run_id

        class FakeProcess:
            pid = 9876

            def poll(self):
                return None

        with (
            mock.patch.object(agent_module.service, "resolve_root", return_value=self.repo),
            mock.patch.object(agent_module.subprocess, "Popen", return_value=FakeProcess()) as popen,
        ):
            response = agent_message(
                self.repo,
                "approve",
                run_id=run_id,
                confirmation=PLAN_CONFIRMATION,
                background=True,
            )

        self.assertTrue(response["background"])
        self.assertEqual(response["job"]["kind"], "agent")
        self.assertEqual(response["job"]["pid"], 9876)
        self.assertTrue((run_path / "AGENT.lock").exists())
        self.assertTrue((run_path / "JOB.json").exists())
        self.assertTrue(popen.call_args.kwargs["env"]["PATCHBAY_INHERITED_AGENT_LOCK"])

    def test_cli_background_agent_approval_completes_in_child_process(self) -> None:
        planned = agent_message(self.repo, "background child process")
        run_id = planned["run_id"]
        run_path = self.repo / ".ai" / "runs" / run_id

        response = self.cli_json(
            "agent",
            "message",
            "approve",
            "--run-id",
            run_id,
            "--confirmation",
            PLAN_CONFIRMATION,
            "--background",
        )

        self.assertTrue(response["background"])
        self.wait_for(lambda: not (run_path / "AGENT.lock").exists() and json.loads((run_path / "STATUS.json").read_text(encoding="utf-8"))["status"] == "REVIEWED_PASS")

        status = json.loads((run_path / "STATUS.json").read_text(encoding="utf-8"))
        self.assertEqual(status["status"], "REVIEWED_PASS")
        self.assertTrue(status["gate_state"]["ready_to_apply"] if "gate_state" in status else status["tests_passed"])

    def test_web_agent_message_endpoint(self) -> None:
        from scripts.ai_flow.web_server import create_server

        import threading

        server = create_server(self.repo, host="127.0.0.1", port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 2)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        host, port = server.server_address
        request = urllib.request.Request(
            f"http://{host}:{port}/api/agent/message",
            data=json.dumps({"message": "web agent task"}).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))

        self.assertEqual(payload["status"]["status"], "PLANNED")
        self.assertEqual(payload["requires_confirmation"]["confirmation"], PLAN_CONFIRMATION)


if __name__ == "__main__":
    unittest.main()
