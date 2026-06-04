from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


class DoctorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="patchbay-doctor-"))
        subprocess.run(["git", "init"], cwd=str(self.tmp), capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "patchbay@example.test"], cwd=str(self.tmp), capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "Patchbay Test"], cwd=str(self.tmp), capture_output=True, check=True)
        (self.tmp / "README.md").write_text("# test\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=str(self.tmp), capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=str(self.tmp), capture_output=True, check=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_unified_doctor_reports_missing_init_without_mcp_probe(self) -> None:
        from scripts.ai_flow.doctor import run_doctor

        result = run_doctor(self.tmp, include_mcp=False)

        self.assertFalse(result["ok"])
        self.assertTrue(result["checks"]["repo"]["git_repo"])
        self.assertIn(".ai/patchbay.example.toml", result["checks"]["repo"]["missing_files"])
        self.assertTrue(result["checks"]["mcp"]["skipped"])
        self.assertTrue(any("patchbay init" in action for action in result["next_actions"]))
        actions = {item["id"]: item for item in result["actions"]}
        self.assertEqual(actions["probe_mcp"]["command"], "patchbay doctor --host codex --probe-mcp --json")
        self.assertEqual(actions["probe_mcp"]["host"], "codex")
        action_groups = {item["id"]: item for item in result["action_groups"]}
        self.assertIn("probe_mcp", action_groups["setup"]["action_ids"])

    def test_unified_doctor_can_suppress_mcp_followups_for_local_only_readiness(self) -> None:
        from scripts.ai_flow.doctor import run_doctor

        result = run_doctor(self.tmp, include_mcp=False, suppress_mcp_actions=True, host="Claude Desktop")

        self.assertFalse(result["ok"])
        self.assertTrue(result["checks"]["mcp"]["skipped"])
        self.assertFalse(any("probe-mcp" in action.lower() or "mcp install" in action.lower() for action in result["next_actions"]))
        actions = {item["id"]: item for item in result["actions"]}
        self.assertNotIn("probe_mcp", actions)
        self.assertNotIn("install_mcp", actions)
        self.assertEqual(result["host"], "claude-desktop")

    def test_doctor_structured_mcp_action_uses_target_host(self) -> None:
        from scripts.ai_flow import doctor

        with mock.patch.object(doctor, "run_mcp_doctor", return_value={"server_reachable": False, "required_tools_present": False}):
            result = doctor.run_doctor(self.tmp, include_mcp=True, host="Claude Desktop")

        actions = {item["id"]: item for item in result["actions"]}
        self.assertEqual(result["host"], "claude-desktop")
        self.assertEqual(actions["install_mcp"]["command"], "patchbay mcp install claude-desktop")
        self.assertEqual(actions["install_mcp"]["host"], "claude-desktop")
        self.assertTrue(any("patchbay mcp install claude-desktop" in action for action in result["next_actions"]))
        self.assertFalse(any("<host>" in action for action in result["next_actions"]))

    def test_unified_doctor_accepts_initialized_project(self) -> None:
        from scripts.ai_flow import service
        from scripts.ai_flow.doctor import run_doctor

        service.init_project(self.tmp)
        with mock.patch.dict("os.environ", {"CODEX_HOME": str(self.tmp / "codex-home")}):
            result = run_doctor(self.tmp, include_mcp=False)

        self.assertTrue(result["checks"]["repo"]["ok"])
        self.assertTrue(result["checks"]["config"]["ok"])
        self.assertTrue(result["checks"]["cli"]["ok"])
        self.assertTrue(result["checks"]["skill"]["source_exists"])
        self.assertEqual(result["checks"]["skill"]["contract"]["kind"], "progressive-skill")
        self.assertEqual(result["checks"]["skill"]["contract"]["entrypoint"], "skills/patchbay/SKILL.md")
        self.assertFalse(result["checks"]["skill"]["installed"])
        self.assertFalse(result["ok"])
        self.assertTrue(any("skill install codex" in action for action in result["next_actions"]))
        actions = {item["id"]: item for item in result["actions"]}
        self.assertEqual(actions["install_skill"]["kind"], "local_agent")
        self.assertEqual(actions["install_skill"]["message"], "install Codex Skill")
        self.assertEqual(actions["install_skill"]["command"], "patchbay skill install codex")

    def test_unified_doctor_surfaces_outdated_skill_update_action(self) -> None:
        from scripts.ai_flow import service
        from scripts.ai_flow.doctor import run_doctor
        from scripts.ai_flow.skill_install import run_skill_install

        service.init_project(self.tmp)
        skills_root = self.tmp / "skills"
        run_skill_install(self.tmp, path=skills_root)
        installed_skill = skills_root / "patchbay" / "SKILL.md"
        installed_skill.write_text(installed_skill.read_text(encoding="utf-8") + "\n# stale local copy\n", encoding="utf-8")

        result = run_doctor(self.tmp, include_mcp=False, skill_path=skills_root)

        self.assertFalse(result["ok"])
        skill = result["checks"]["skill"]
        self.assertTrue(skill["ok"])
        self.assertFalse(skill["ready"])
        self.assertEqual(skill["status"], "outdated")
        self.assertFalse(skill["installed_matches_source"])
        self.assertIn("SKILL.md", skill["changed_installed_files"])
        self.assertEqual(skill["extra_installed_files"], [])
        self.assertTrue(any("update the installed Patchbay Skill" in action for action in result["next_actions"]))
        actions = {item["id"]: item for item in result["actions"]}
        self.assertEqual(actions["install_skill"]["label"], "Update Codex Skill")
        self.assertEqual(actions["install_skill"]["kind"], "command")
        self.assertNotIn("message", actions["install_skill"])
        self.assertIn("patchbay skill install codex", actions["install_skill"]["command"])
        self.assertIn(str(skills_root), actions["install_skill"]["command"])
        self.assertIn("selected Codex skills root", actions["install_skill"]["reason"])
        action_groups = {item["id"]: item for item in result["action_groups"]}
        self.assertIn("install_skill", action_groups["setup"]["action_ids"])

    def test_cli_check_detects_installed_console_scripts_without_path(self) -> None:
        from scripts.ai_flow import doctor

        scripts_dir = self.tmp / "venv" / "Scripts"
        scripts_dir.mkdir(parents=True)
        patchbay = scripts_dir / "patchbay.exe"
        patchbay_mcp = scripts_dir / "patchbay-mcp.exe"
        python = scripts_dir / "python.exe"
        patchbay.write_text("", encoding="utf-8")
        patchbay_mcp.write_text("", encoding="utf-8")
        python.write_text("", encoding="utf-8")

        with (
            mock.patch.object(doctor.shutil, "which", return_value=None),
            mock.patch.object(doctor.sys, "argv", [str(patchbay)]),
            mock.patch.object(doctor.sys, "executable", str(python)),
        ):
            result = doctor._cli_check(self.tmp)

        self.assertTrue(result["ok"])
        self.assertEqual(Path(result["entrypoint"]), patchbay)
        self.assertTrue(result["entrypoint_exists"])
        self.assertEqual(Path(result["mcp_command"]), patchbay_mcp)
        self.assertTrue(result["mcp_command_exists"])
        self.assertFalse(result["command_exists"])

    def test_doctor_exposes_custom_profile_contract_without_mcp_probe(self) -> None:
        from scripts.ai_flow import service
        from scripts.ai_flow.doctor import run_doctor

        service.init_project(self.tmp)
        config_path = self.tmp / ".ai" / "patchbay.toml"
        config_path.write_text(
            """[phases.plan]
provider = "mock"

[phases.write]
provider = "mock"

[phases.review]
provider = "mock"

[phases.fix]
provider = "mock"
""",
            encoding="utf-8",
        )

        result = run_doctor(self.tmp, include_mcp=False, skill_path=self.tmp / "skills")
        profile = result["checks"]["config"]["profile"]

        self.assertEqual(profile["profile"], "custom")
        self.assertFalse(profile["economy"]["matches"])
        self.assertEqual(profile["economy"]["write"]["provider"], "mock")
        self.assertEqual(profile["economy"]["fix"]["provider"], "mock")
        self.assertEqual(profile["phase_strategy"]["write"]["tier"], "economy")
        self.assertFalse(profile["phase_strategy"]["write"]["economy_route"])
        self.assertEqual(result["routing"]["profile"], "custom")
        self.assertFalse(result["routing"]["economy_configured"])
        self.assertEqual(result["routing"]["workload_policy"]["economy_phases"], ["write", "fix"])
        self.assertEqual(result["routing"]["workload_policy"]["supervision_phases"], ["plan", "review"])
        self.assertTrue(result["checks"]["mcp"]["skipped"])
        self.assertTrue(any("patchbay config profile apply economy" in item for item in result["recommendations"]))

    def test_doctor_recommends_reasonix_command_for_economy_profile(self) -> None:
        from scripts.ai_flow import service
        from scripts.ai_flow.doctor import run_doctor

        service.init_project(self.tmp)

        result = run_doctor(self.tmp, include_mcp=False, skill_path=self.tmp / "skills")

        profile = result["checks"]["config"]["profile"]
        self.assertEqual(profile["profile"], "economy")
        self.assertFalse(profile["economy"]["command_ready"])
        self.assertEqual(result["routing"]["profile"], "economy")
        self.assertTrue(result["routing"]["economy_configured"])
        self.assertFalse(result["routing"]["economy_command_ready"])
        self.assertEqual(result["routing"]["workload_policy"]["target_label"], "Reasonix/DeepSeek")
        self.assertTrue(any("commands.reasonix" in item for item in result["recommendations"]))
        actions = {item["id"]: item for item in result["actions"]}
        self.assertEqual(actions["configure_reasonix_command"]["kind"], "local_agent")
        self.assertEqual(actions["configure_reasonix_command"]["message"], "configure reasonix command")
        self.assertIn("commands.reasonix", actions["configure_reasonix_command"]["command"])
        self.assertEqual(actions["configure_deepseek_provider"]["kind"], "local_agent")
        self.assertEqual(actions["configure_deepseek_provider"]["message"], "configure DeepSeek provider")
        self.assertNotIn("apply_economy_profile", actions)
        action_groups = {item["id"]: item for item in result["action_groups"]}
        self.assertIn("configure_reasonix_command", action_groups["routing"]["action_ids"])

    def test_doctor_ready_state_offers_safe_followups(self) -> None:
        from scripts.ai_flow import service
        from scripts.ai_flow.doctor import run_doctor
        from scripts.ai_flow.skill_install import run_skill_install

        service.init_project(self.tmp)
        skills_root = self.tmp / "skills"
        run_skill_install(self.tmp, path=skills_root)
        config_path = self.tmp / ".ai" / "patchbay.toml"
        escaped = sys.executable.replace("\\", "\\\\")
        config_path.write_text(
            f"""[commands]
reasonix = "{escaped}"
""",
            encoding="utf-8",
        )

        result = run_doctor(self.tmp, include_mcp=False, skill_path=skills_root, suppress_mcp_actions=True)

        self.assertTrue(result["ok"])
        self.assertEqual(result["recommendations"], [])
        self.assertEqual(result["next_actions"], [])
        self.assertTrue(result["routing"]["economy_command_ready"])
        actions = {item["id"]: item for item in result["actions"]}
        self.assertEqual(actions["start_new_task"]["kind"], "focus_composer")
        self.assertEqual(actions["show_runs"]["message"], "status")
        action_groups = {item["id"]: item for item in result["action_groups"]}
        self.assertIn("start_new_task", action_groups["new_task"]["action_ids"])
        self.assertIn("show_runs", action_groups["local"]["action_ids"])

    def test_doctor_recommends_custom_economy_provider_command(self) -> None:
        from scripts.ai_flow import service
        from scripts.ai_flow.doctor import run_doctor

        service.init_project(self.tmp)
        (self.tmp / ".ai" / "patchbay.toml").write_text(
            """
[providers.cheap_writer]
roles = ["write", "fix"]
command = "definitely-missing-cheap-writer"
prompt_mode = "stdin"
output_contract = "writer_diff"

[profiles.economy]
provider = "cheap_writer"
model = "cheap-model"
label = "Cheap writer"

[phases.write]
provider = "cheap_writer"
model = "cheap-model"

[phases.fix]
provider = "cheap_writer"
model = "cheap-model"
""".lstrip(),
            encoding="utf-8",
        )

        result = run_doctor(self.tmp, include_mcp=False, skill_path=self.tmp / "skills")

        profile = result["checks"]["config"]["profile"]
        self.assertEqual(profile["profile"], "economy")
        self.assertFalse(profile["economy"]["command_ready"])
        self.assertTrue(any("providers.cheap_writer.command" in item for item in result["recommendations"]))
        action_ids = [item["id"] for item in result["actions"]]
        self.assertLess(
            action_ids.index("configure_economy_provider_command"),
            action_ids.index("inspect_economy_provider_command"),
        )
        actions = {item["id"]: item for item in result["actions"]}
        self.assertIn("inspect_economy_provider_command", actions)
        self.assertEqual(actions["configure_economy_provider_command"]["kind"], "command")
        self.assertEqual(
            actions["configure_economy_provider_command"]["command"],
            "patchbay config --set-key providers.cheap_writer.command --set-value <command>",
        )
        self.assertNotIn("configure_reasonix_command", actions)


if __name__ == "__main__":
    unittest.main()
