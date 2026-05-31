from __future__ import annotations

import shutil
import subprocess
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
        result = run_doctor(self.tmp, include_mcp=False, skill_path=self.tmp / "skills")

        self.assertTrue(result["checks"]["repo"]["ok"])
        self.assertTrue(result["checks"]["config"]["ok"])
        self.assertTrue(result["checks"]["cli"]["ok"])
        self.assertTrue(result["checks"]["skill"]["source_exists"])
        self.assertFalse(result["checks"]["skill"]["installed"])
        self.assertFalse(result["ok"])
        self.assertTrue(any("skill install codex" in action for action in result["next_actions"]))

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
        self.assertTrue(any("commands.reasonix" in item for item in result["recommendations"]))
        actions = {item["id"]: item for item in result["actions"]}
        self.assertEqual(actions["configure_reasonix_command"]["kind"], "local_agent")
        self.assertEqual(actions["configure_reasonix_command"]["message"], "configure reasonix command")
        self.assertIn("commands.reasonix", actions["configure_reasonix_command"]["command"])
        self.assertNotIn("apply_economy_profile", actions)

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
        actions = {item["id"]: item for item in result["actions"]}
        self.assertIn("inspect_economy_provider_command", actions)
        self.assertNotIn("configure_reasonix_command", actions)


if __name__ == "__main__":
    unittest.main()
