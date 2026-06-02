from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import tomllib


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class SkillInstallTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="patchbay-skill-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_skill_print_includes_required_files(self) -> None:
        from scripts.ai_flow.skill_install import run_skill_print

        result = run_skill_print(self.tmp)

        self.assertIn("SKILL.md", result["files"])
        self.assertIn("agents/openai.yaml", result["files"])
        self.assertIn("references/install.md", result["files"])
        self.assertIn("Recommended Conversational Entry", result["files"]["SKILL.md"])
        self.assertIn('scripts/patchbay agent message "<user task>" --background --json', result["files"]["SKILL.md"])
        self.assertIn("Use this manual phase workflow when the conversational Agent tool is unavailable", result["files"]["SKILL.md"])
        self.assertIn("Patchbay's conversational agent", result["files"]["agents/openai.yaml"])
        self.assertIn("inspect economy routing evidence", result["files"]["agents/openai.yaml"])
        self.assertIn("patchbay_agent", result["files"]["SKILL.md"])
        self.assertIn("do not call `patchbay_*` MCP tools", result["files"]["SKILL.md"])
        self.assertIn('scripts/patchbay setup --no-mcp --json', result["files"]["SKILL.md"])
        self.assertIn('scripts/patchbay doctor --local-only --json', result["files"]["SKILL.md"])
        self.assertIn('scripts/patchbay agent message "patchbay setup without MCP" --json', result["files"]["SKILL.md"])
        self.assertIn('scripts/patchbay agent message "readiness without MCP" --json', result["files"]["SKILL.md"])
        self.assertIn("patchbay setup for Claude Desktop", result["files"]["SKILL.md"])
        self.assertIn("帮我配置 Patchbay", result["files"]["SKILL.md"])
        self.assertIn("Patchbay 怎么用", result["files"]["SKILL.md"])
        self.assertIn("查看最近运行", result["files"]["SKILL.md"])
        self.assertIn("查看失败原因", result["files"]["SKILL.md"])
        self.assertIn("what should I do next", result["files"]["SKILL.md"])
        self.assertIn("下一步是什么", result["files"]["SKILL.md"])
        self.assertIn('action: "next_step"', result["files"]["SKILL.md"])
        self.assertIn("run_reference.next_action", result["files"]["SKILL.md"])
        self.assertIn("what is blocking apply", result["files"]["SKILL.md"])
        self.assertIn("what model will write/fix use", result["files"]["SKILL.md"])
        self.assertIn("is writer using cheap model", result["files"]["SKILL.md"])
        self.assertIn("门禁状态", result["files"]["SKILL.md"])
        self.assertIn("现在写手是不是走便宜模型", result["files"]["SKILL.md"])
        self.assertIn('action: "gate_status"', result["files"]["SKILL.md"])
        self.assertIn("profile_show", result["files"]["SKILL.md"])
        self.assertIn("read-only `profile`, `routing`, safe `actions[]`, and `action_groups[]` preview", result["files"]["SKILL.md"])
        self.assertIn("When `action_groups[]` is present", result["files"]["SKILL.md"])
        self.assertIn("background_polling", result["files"]["SKILL.md"])
        self.assertIn("gate_diagnosis", result["files"]["SKILL.md"])
        self.assertIn("readiness for Claude Desktop", result["files"]["SKILL.md"])
        self.assertIn("检查 Gemini 命令行环境", result["files"]["SKILL.md"])
        self.assertIn("install Codex Skill", result["files"]["SKILL.md"])
        self.assertIn("register MCP for Claude Desktop", result["files"]["SKILL.md"])
        self.assertIn("安装 Codex Skill", result["files"]["SKILL.md"])
        self.assertIn("注册 MCP 到 Gemini 命令行", result["files"]["SKILL.md"])
        self.assertIn("configure reasonix command", result["files"]["SKILL.md"])
        self.assertIn("configure reasonix command to <path>", result["files"]["SKILL.md"])
        self.assertIn("configure DeepSeek provider", result["files"]["SKILL.md"])
        self.assertIn("configure DeepSeek provider to <command>", result["files"]["SKILL.md"])
        self.assertIn("providers.<id>.command", result["files"]["SKILL.md"])
        local_prompt_list = result["files"]["SKILL.md"].split(
            "- `patchbay_agent` for conversational setup/start/resume/advance while preserving gates. It also answers explicit local prompts such as ",
            1,
        )[1].split(" with setup results", 1)[0]
        self.assertIn("configure DeepSeek provider", local_prompt_list)
        self.assertIn("configure DeepSeek provider to <command>", local_prompt_list)
        self.assertIn("configure economy provider command to <path>", local_prompt_list)
        self.assertIn("配置 Reasonix 命令", result["files"]["SKILL.md"])
        self.assertIn("把 Reasonix 命令设为 <path>", result["files"]["SKILL.md"])
        self.assertIn("command_not_ready", result["files"]["SKILL.md"])
        self.assertIn("patchbay_doctor(skip_mcp=true)", result["files"]["SKILL.md"])
        self.assertIn("skip_mcp: true", result["files"]["SKILL.md"])
        self.assertIn("install patchbay for Gemini CLI", result["files"]["references/install.md"])
        self.assertIn("python scripts/patchbay setup --host codex --no-mcp", result["files"]["references/install.md"])
        self.assertIn("python scripts/patchbay doctor --local-only --json", result["files"]["references/install.md"])
        self.assertIn("configure DeepSeek provider", result["files"]["references/install.md"])
        self.assertIn("configure DeepSeek provider to <command>", result["files"]["references/install.md"])
        self.assertIn("providers.<id>.command", result["files"]["references/install.md"])
        self.assertIn("configure reasonix command", result["files"]["references/install.md"])
        self.assertIn("configure reasonix command to <path>", result["files"]["references/install.md"])
        self.assertIn("configure_reasonix_command", result["files"]["references/install.md"])

    def test_bundled_skill_matches_install_template(self) -> None:
        template_root = PROJECT_ROOT / "scripts" / "ai_flow" / "skill_templates" / "patchbay"
        bundled_root = PROJECT_ROOT / "skills" / "patchbay"
        for relative in (
            Path("SKILL.md"),
            Path("references/install.md"),
        ):
            self.assertEqual(
                (template_root / relative).read_text(encoding="utf-8"),
                (bundled_root / relative).read_text(encoding="utf-8"),
                f"{relative.as_posix()} drifted between the install template and bundled skill",
            )

    def test_package_data_includes_skill_template_bundle(self) -> None:
        data = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        package_data = data["tool"]["setuptools"]["package-data"]["ai_flow"]

        self.assertIn("skill_templates/**", package_data)
        for required in (
            "SKILL.md",
            "agents/openai.yaml",
            "references/install.md",
        ):
            self.assertTrue((PROJECT_ROOT / "scripts" / "ai_flow" / "skill_templates" / "patchbay" / required).exists())

    def test_pyproject_has_clean_wheel_metadata_for_data_dirs(self) -> None:
        data = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

        self.assertEqual(data["project"]["license"], "MIT")
        self.assertFalse(any("License :: OSI Approved" in item for item in data["project"]["classifiers"]))
        packages = data["tool"]["setuptools"]["packages"]
        for package in (
            "ai_flow.skill_templates",
            "ai_flow.skill_templates.patchbay",
            "ai_flow.skill_templates.patchbay.agents",
            "ai_flow.skill_templates.patchbay.references",
            "ai_flow.web_static",
            "ai_flow.web_static.assets",
        ):
            self.assertIn(package, packages)

    def test_skill_install_copies_bundle(self) -> None:
        from scripts.ai_flow.skill_install import run_skill_install

        target = self.tmp / "skills-root"
        result = run_skill_install(self.tmp, path=target)

        destination = target / "patchbay"
        self.assertTrue(result["installed"])
        self.assertEqual(Path(result["destination"]), destination)
        self.assertTrue((destination / "SKILL.md").exists())
        self.assertTrue((destination / "agents" / "openai.yaml").exists())
        self.assertIn("patchbay setup for Claude Desktop", (destination / "SKILL.md").read_text(encoding="utf-8"))

    def test_skill_install_dry_run_does_not_copy(self) -> None:
        from scripts.ai_flow.skill_install import run_skill_install

        target = self.tmp / "skills-root"
        result = run_skill_install(self.tmp, path=target, dry_run=True)

        self.assertTrue(result["dry_run"])
        self.assertFalse((target / "patchbay").exists())

    def test_skill_commands_accept_codex_host_aliases(self) -> None:
        from scripts.ai_flow.skill_install import run_skill_doctor, run_skill_install, run_skill_print

        target = self.tmp / "skills-root"
        install = run_skill_install(self.tmp, host="Codex 桌面", path=target, dry_run=True)
        self.assertEqual(install["host"], "codex")
        self.assertTrue(install["dry_run"])

        printed = run_skill_print(self.tmp, host="Codex Desktop")
        self.assertEqual(printed["host"], "codex")
        self.assertIn("SKILL.md", printed["files"])

        doctor = run_skill_doctor(self.tmp, host="Codex CLI", path=target)
        self.assertEqual(doctor["host"], "codex")
        self.assertTrue(doctor["ok"])

    def test_skill_commands_reject_non_codex_hosts(self) -> None:
        from scripts.ai_flow.errors import AiFlowError
        from scripts.ai_flow.skill_install import run_skill_doctor

        with self.assertRaises(AiFlowError) as raised:
            run_skill_doctor(self.tmp, host="Claude Desktop", path=self.tmp / "skills-root")

        self.assertEqual(raised.exception.stage, "skill")
        self.assertIn("Only the Codex Skill currently supports diagnostics", str(raised.exception))
        self.assertIn("Accepted Codex aliases", str(raised.exception))

    def test_mcp_skill_tools_accept_codex_aliases(self) -> None:
        from scripts.ai_flow import mcp_server

        target = self.tmp / "skills-root"
        response = mcp_server.handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "patchbay_skill_doctor",
                    "arguments": {"host": "Codex Desktop", "skill_path": str(target)},
                },
            }
        )

        self.assertFalse(response["result"].get("isError"), response)
        result = json.loads(response["result"]["content"][0]["text"])
        self.assertEqual(result["host"], "codex")
        self.assertTrue(result["ok"])

    def test_cli_skill_doctor_json_reports_ready_state(self) -> None:
        script = PROJECT_ROOT / "scripts" / "patchbay"
        target = self.tmp / "skills-root"
        completed = subprocess.run(
            ["python", str(script), "skill", "doctor", "codex", "--path", str(target), "--json"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertTrue(result["ok"])
        self.assertFalse(result["ready"])
        self.assertEqual(result["status"], "not_installed")

    def test_skill_doctor_reports_source_and_install_state(self) -> None:
        from scripts.ai_flow.skill_install import run_skill_doctor, run_skill_install

        with patch.dict(os.environ, {"CODEX_HOME": str(self.tmp / "codex-home")}):
            default_before = run_skill_doctor(self.tmp)
        default_actions = {item["id"]: item for item in default_before["actions"]}
        default_groups = {item["id"]: item for item in default_before["action_groups"]}
        self.assertEqual(default_actions["install_skill"]["kind"], "local_agent")
        self.assertEqual(default_actions["install_skill"]["message"], "install Codex Skill")
        self.assertEqual(default_actions["install_skill"]["host"], "codex")
        self.assertEqual(default_actions["install_skill"]["command"], "patchbay skill install codex")
        self.assertIn("install_skill", default_groups["setup"]["action_ids"])

        target = self.tmp / "skills-root"
        before = run_skill_doctor(self.tmp, path=target)
        self.assertTrue(before["ok"])
        self.assertFalse(before["ready"])
        self.assertEqual(before["status"], "not_installed")
        self.assertTrue(before["source_exists"])
        self.assertFalse(before["installed"])
        self.assertTrue(any("skill install codex" in action for action in before["next_actions"]))
        before_actions = {item["id"]: item for item in before["actions"]}
        before_groups = {item["id"]: item for item in before["action_groups"]}
        self.assertEqual(before_actions["install_skill"]["kind"], "command")
        self.assertNotIn("message", before_actions["install_skill"])
        self.assertIn("patchbay skill install codex", before_actions["install_skill"]["command"])
        self.assertIn(str(target), before_actions["install_skill"]["command"])
        self.assertEqual(before_actions["refresh_skill_doctor"]["kind"], "command")
        self.assertIn("--json", before_actions["refresh_skill_doctor"]["command"])
        self.assertIn("install_skill", before_groups["setup"]["action_ids"])
        self.assertIn("refresh_skill_doctor", before_groups["setup"]["action_ids"])

        installed = run_skill_install(self.tmp, path=target)
        installed_actions = {item["id"]: item for item in installed["actions"]}
        installed_groups = {item["id"]: item for item in installed["action_groups"]}
        self.assertIn("refresh_skill_doctor", installed_actions)
        self.assertIn(str(target), installed_actions["refresh_skill_doctor"]["command"])
        self.assertIn("refresh_skill_doctor", installed_groups["setup"]["action_ids"])
        after = run_skill_doctor(self.tmp, path=target)
        self.assertTrue(after["ok"])
        self.assertTrue(after["ready"])
        self.assertEqual(after["status"], "installed")
        self.assertTrue(after["installed"])
        self.assertEqual(Path(after["destination"]), target / "patchbay")
        self.assertEqual(after["next_actions"], [])
        self.assertEqual(after["actions"], [])
        self.assertEqual(after["action_groups"], [])


if __name__ == "__main__":
    unittest.main()
