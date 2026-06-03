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
        skill = result["files"]["SKILL.md"]
        contract = result["files"]["references/agent-contract.md"]
        install = result["files"]["references/install.md"]
        contract_summary = result["contract"]

        self.assertIn("SKILL.md", result["files"])
        self.assertIn("agents/openai.yaml", result["files"])
        self.assertIn("references/install.md", result["files"])
        self.assertIn("references/agent-contract.md", result["files"])
        self.assertLess(len(skill), 9000)
        self.assertIn("Entry Choice", skill)
        self.assertIn('scripts/patchbay agent message "<user task>" --background --json', skill)
        self.assertIn("Read `references/agent-contract.md` only when", skill)
        self.assertIn("Do not call `patchbay_*` MCP tools", skill)
        self.assertIn('scripts/patchbay setup --no-mcp --json', skill)
        self.assertIn('scripts/patchbay doctor --local-only --json', skill)
        self.assertIn('scripts/patchbay agent message "patchbay setup without MCP" --json', skill)
        self.assertIn('scripts/patchbay agent message "readiness without MCP" --json', skill)
        self.assertIn('scripts/patchbay agent message "走本地模式，不走 MCP" --json', skill)
        self.assertIn("只用本地工具", skill)
        self.assertIn("Required Gates", skill)
        self.assertIn("Never apply without a separate explicit apply confirmation", skill)
        self.assertIn("cheaper economy route", skill)
        self.assertIn("完全访问权限", skill)
        self.assertIn("Patchbay's conversational agent", result["files"]["agents/openai.yaml"])
        self.assertIn("inspect economy routing evidence", result["files"]["agents/openai.yaml"])
        self.assertIn("Patchbay Agent Contract", contract)
        self.assertIn("patchbay_agent", contract)
        self.assertIn("patchbay setup for Claude Desktop", contract)
        self.assertIn("帮我配置 Patchbay", contract)
        self.assertIn("Patchbay 怎么用", contract)
        self.assertIn("查看最近运行", contract)
        self.assertIn("查看失败原因", contract)
        self.assertIn("what should I do next", contract)
        self.assertIn("下一步是什么", contract)
        self.assertIn('action: "next_step"', contract)
        self.assertIn("run_reference.next_action", contract)
        self.assertIn("what is blocking apply", contract)
        self.assertIn("what model will write/fix use", contract)
        self.assertIn("is writer using cheap model", contract)
        self.assertIn("门禁状态", contract)
        self.assertIn("现在写手是不是走便宜模型", contract)
        self.assertIn('action: "gate_status"', contract)
        self.assertIn("profile_show", contract)
        self.assertIn("capabilities[]", contract)
        self.assertIn("Agent help surface", contract)
        self.assertIn("gate_diagnosis.next_action", contract)
        self.assertIn("action_groups[]", contract)
        self.assertIn("background_polling", contract)
        self.assertIn("full access", contract)
        self.assertIn("无需向我确认", contract)
        self.assertIn("failure_recovery", contract)
        self.assertIn("readiness for Claude Desktop", contract)
        self.assertIn("检查 Gemini 命令行环境", contract)
        self.assertIn("install Codex Skill", contract)
        self.assertIn("register MCP for Claude Desktop", contract)
        self.assertIn("安装 Codex Skill", contract)
        self.assertIn("注册 MCP 到 Gemini 命令行", contract)
        self.assertIn("configure reasonix command", contract)
        self.assertIn("configure reasonix command to <path>", contract)
        self.assertIn("configure DeepSeek provider", contract)
        self.assertIn("configure DeepSeek provider to <command>", contract)
        self.assertIn("configure economy provider command to <path>", contract)
        self.assertIn("简单 writer/fix 用 DeepSeek 省钱", contract)
        self.assertIn("guarded economy-provider form", contract)
        self.assertIn("providers.<id>.command", contract)
        self.assertIn("配置 Reasonix 命令", contract)
        self.assertIn("把 Reasonix 命令设为 <path>", contract)
        self.assertIn("command_not_ready", contract)
        self.assertIn("patchbay_doctor(skip_mcp=true)", contract)
        self.assertIn("skip_mcp: true", contract)
        self.assertIn("install patchbay for Gemini CLI", install)
        self.assertIn("python scripts/patchbay setup --host codex --no-mcp", install)
        self.assertIn("python scripts/patchbay doctor --local-only --json", install)
        self.assertIn('python scripts/patchbay agent message "走本地模式，不走 MCP" --json', install)
        self.assertIn("configure DeepSeek provider", install)
        self.assertIn("configure DeepSeek provider to <command>", install)
        self.assertIn("简单 writer/fix 用 DeepSeek 省钱", install)
        self.assertIn("guarded economy-provider form", install)
        self.assertIn("只用本地工具", install)
        self.assertIn('status: "outdated"', install)
        self.assertIn("installed_matches_source", install)
        self.assertIn("missing_installed_files", install)
        self.assertIn("changed_installed_files", install)
        self.assertIn("extra_installed_files", install)
        self.assertIn("providers.<id>.command", install)
        self.assertIn("configure reasonix command", install)
        self.assertIn("configure reasonix command to <path>", install)
        self.assertIn("configure_reasonix_command", install)
        self.assertEqual(contract_summary["kind"], "progressive-skill")
        self.assertEqual(contract_summary["entrypoint"], "skills/patchbay/SKILL.md")
        self.assertIn("patchbay skill doctor codex --json", contract_summary["commands"])
        self.assertIn("skills/patchbay/references/agent-contract.md", {item["path"] for item in contract_summary["references"]})

    def test_bundled_skill_matches_install_template(self) -> None:
        template_root = PROJECT_ROOT / "scripts" / "ai_flow" / "skill_templates" / "patchbay"
        bundled_root = PROJECT_ROOT / "skills" / "patchbay"
        for relative in (
            Path("SKILL.md"),
            Path("agents/openai.yaml"),
            Path("references/agent-contract.md"),
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
            "references/agent-contract.md",
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
        self.assertTrue((destination / "references" / "agent-contract.md").exists())
        self.assertIn("references/agent-contract.md", (destination / "SKILL.md").read_text(encoding="utf-8"))
        self.assertIn("patchbay setup for Claude Desktop", (destination / "references" / "agent-contract.md").read_text(encoding="utf-8"))

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
        self.assertEqual(printed["contract"]["kind"], "progressive-skill")

        doctor = run_skill_doctor(self.tmp, host="Codex CLI", path=target)
        self.assertEqual(doctor["host"], "codex")
        self.assertTrue(doctor["ok"])
        self.assertEqual(doctor["contract"]["entrypoint"], "skills/patchbay/SKILL.md")

    def test_skill_commands_reject_non_codex_hosts(self) -> None:
        from scripts.ai_flow.errors import AiFlowError
        from scripts.ai_flow.skill_install import run_skill_doctor

        with self.assertRaises(AiFlowError) as raised:
            run_skill_doctor(self.tmp, host="Claude Desktop", path=self.tmp / "skills-root")

        self.assertEqual(raised.exception.stage, "skill")
        self.assertIn("Only the Codex Skill currently supports diagnostics", str(raised.exception))
        self.assertIn("Accepted Codex aliases", str(raised.exception))

    def test_skill_doctor_requires_agent_contract_reference(self) -> None:
        from scripts.ai_flow import skill_install

        source = self.tmp / "source" / "patchbay"
        (source / "agents").mkdir(parents=True)
        (source / "references").mkdir()
        (source / "SKILL.md").write_text("---\nname: patchbay\ndescription: test\n---\n", encoding="utf-8")
        (source / "agents" / "openai.yaml").write_text("display_name: Patchbay\n", encoding="utf-8")
        (source / "references" / "install.md").write_text("# install\n", encoding="utf-8")

        with patch.object(skill_install, "SKILL_SOURCE_CANDIDATES", [source]):
            result = skill_install.run_skill_doctor(self.tmp, path=self.tmp / "skills-root")

        self.assertFalse(result["ok"])
        self.assertFalse(result["ready"])
        self.assertEqual(result["status"], "missing_source")
        self.assertIn("references/agent-contract.md", result["missing_source_files"])

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
        self.assertEqual(before["contract"]["kind"], "progressive-skill")
        self.assertIn("failure_recovery", before["contract"]["structured_fields"])
        self.assertFalse(before["installed"])
        self.assertFalse(before["installed_matches_source"])
        self.assertEqual(before["missing_installed_files"], [])
        self.assertEqual(before["changed_installed_files"], [])
        self.assertEqual(before["extra_installed_files"], [])
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
        self.assertTrue(after["installed_matches_source"])
        self.assertEqual(after["missing_installed_files"], [])
        self.assertEqual(after["changed_installed_files"], [])
        self.assertEqual(after["extra_installed_files"], [])
        self.assertEqual(Path(after["destination"]), target / "patchbay")
        self.assertEqual(after["next_actions"], [])
        self.assertEqual(after["actions"], [])
        self.assertEqual(after["action_groups"], [])

    def test_skill_doctor_reports_outdated_installed_skill(self) -> None:
        from scripts.ai_flow.skill_install import run_skill_doctor, run_skill_install

        target = self.tmp / "skills-root"
        run_skill_install(self.tmp, path=target)
        installed_skill = target / "patchbay" / "SKILL.md"
        installed_skill.write_text(installed_skill.read_text(encoding="utf-8") + "\n# stale local edit\n", encoding="utf-8")

        result = run_skill_doctor(self.tmp, path=target)

        self.assertTrue(result["ok"])
        self.assertTrue(result["installed"])
        self.assertFalse(result["ready"])
        self.assertEqual(result["status"], "outdated")
        self.assertFalse(result["installed_matches_source"])
        self.assertIn("SKILL.md", result["changed_installed_files"])
        self.assertEqual(result["missing_installed_files"], [])
        self.assertEqual(result["extra_installed_files"], [])
        self.assertTrue(any("skill install codex" in action for action in result["next_actions"]))
        actions = {item["id"]: item for item in result["actions"]}
        self.assertIn("install_skill", actions)
        self.assertIn(str(target), actions["install_skill"]["command"])
        self.assertIn("refresh_skill_doctor", actions)
        groups = {item["id"]: item for item in result["action_groups"]}
        self.assertIn("install_skill", groups["setup"]["action_ids"])
        self.assertIn("refresh_skill_doctor", groups["setup"]["action_ids"])

    def test_skill_doctor_reports_extra_installed_skill_files(self) -> None:
        from scripts.ai_flow.skill_install import run_skill_doctor, run_skill_install

        target = self.tmp / "skills-root"
        run_skill_install(self.tmp, path=target)
        extra_file = target / "patchbay" / "legacy.md"
        extra_file.write_text("stale file from an older install\n", encoding="utf-8")

        result = run_skill_doctor(self.tmp, path=target)

        self.assertTrue(result["ok"])
        self.assertTrue(result["installed"])
        self.assertFalse(result["ready"])
        self.assertEqual(result["status"], "outdated")
        self.assertFalse(result["installed_matches_source"])
        self.assertEqual(result["missing_installed_files"], [])
        self.assertEqual(result["changed_installed_files"], [])
        self.assertIn("legacy.md", result["extra_installed_files"])
        actions = {item["id"]: item for item in result["actions"]}
        self.assertIn("install_skill", actions)
        self.assertIn(str(target), actions["install_skill"]["command"])


if __name__ == "__main__":
    unittest.main()
