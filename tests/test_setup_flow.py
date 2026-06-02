from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


class SetupFlowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="patchbay-setup-"))
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        self.skills = self.tmp / "skills"
        self.script = PROJECT_ROOT / "scripts" / "patchbay"
        run(["git", "init"], self.repo)
        run(["git", "config", "user.email", "patchbay@example.test"], self.repo)
        run(["git", "config", "user.name", "Patchbay tests"], self.repo)
        (self.repo / "README.md").write_text("# setup repo\n", encoding="utf-8")
        run(["git", "add", "README.md"], self.repo)
        run(["git", "commit", "-m", "initial"], self.repo)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_setup_initializes_config_skill_and_doctor(self) -> None:
        from scripts.ai_flow.setup_flow import run_setup

        result = run_setup(self.repo, skill_path=self.skills, skip_mcp=True)

        self.assertTrue(result["ok"])
        self.assertTrue(result["applied"])
        self.assertTrue((self.repo / "AGENTS.md").exists())
        self.assertTrue((self.repo / ".ai" / "patchbay.example.toml").exists())
        self.assertTrue((self.repo / ".ai" / "patchbay.toml").exists())
        self.assertTrue((self.skills / "patchbay" / "SKILL.md").exists())
        self.assertEqual(result["setup_host"], "codex")
        self.assertTrue(result["config"]["created"])
        self.assertTrue(result["skill"]["installed"])
        self.assertTrue(result["doctor"]["ok"])
        self.assertIn("routing", result)
        self.assertEqual(result["routing"], result["doctor"]["routing"])
        self.assertEqual(result["routing"]["profile"], "economy")
        self.assertEqual(result["routing"]["workload_policy"]["economy_phases"], ["write", "fix"])
        self.assertEqual(result["routing"]["workload_policy"]["supervision_phases"], ["plan", "review"])
        actions = {item["id"]: item for item in result["actions"]}
        doctor_actions = {item["id"]: item for item in result["doctor"]["actions"]}
        self.assertNotIn("probe_mcp", actions)
        self.assertNotIn("install_mcp", actions)
        self.assertNotIn("register_mcp", actions)
        self.assertNotIn("probe_mcp", doctor_actions)
        self.assertNotIn("install_mcp", doctor_actions)
        self.assertNotIn("register_mcp", doctor_actions)
        self.assertFalse(any("probe-mcp" in item.lower() or "mcp install" in item.lower() for item in result["next_actions"]))
        self.assertFalse(any("probe-mcp" in item.lower() or "mcp install" in item.lower() for item in result["doctor"]["next_actions"]))

    def test_setup_dry_run_does_not_write_files(self) -> None:
        from scripts.ai_flow.setup_flow import run_setup

        result = run_setup(self.repo, skill_path=self.skills, skip_mcp=True, dry_run=True)

        self.assertFalse(result["ok"])
        self.assertTrue(result["dry_run"])
        self.assertFalse(result["applied"])
        self.assertTrue(result["config"]["would_create"])
        self.assertFalse((self.repo / "AGENTS.md").exists())
        self.assertFalse((self.repo / ".ai" / "patchbay.toml").exists())
        self.assertFalse((self.skills / "patchbay").exists())
        self.assertEqual(result["setup_host"], "codex")

    def test_setup_dry_run_on_ready_repo_reports_preflight_ok_without_applying(self) -> None:
        from scripts.ai_flow.setup_flow import run_setup

        run_setup(self.repo, skill_path=self.skills, skip_mcp=True)

        result = run_setup(self.repo, skill_path=self.skills, skip_mcp=True, dry_run=True)

        self.assertTrue(result["ok"])
        self.assertTrue(result["dry_run"])
        self.assertFalse(result["applied"])
        self.assertTrue(result["doctor"]["ok"])
        self.assertTrue((self.skills / "patchbay" / "SKILL.md").exists())

    def test_cli_setup_json(self) -> None:
        completed = run(
            [
                "python",
                str(self.script),
                "setup",
                "--skill-path",
                str(self.skills),
                "--no-mcp",
                "--json",
            ],
            self.repo,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertTrue(result["ok"])
        self.assertTrue((self.repo / ".ai" / "patchbay.toml").exists())
        self.assertTrue((self.skills / "patchbay" / "SKILL.md").exists())
        action_ids = {item["id"] for item in result["actions"]}
        doctor_action_ids = {item["id"] for item in result["doctor"]["actions"]}
        self.assertNotIn("probe_mcp", action_ids)
        self.assertNotIn("probe_mcp", doctor_action_ids)

    def test_cli_install_alias_json(self) -> None:
        completed = run(
            [
                "python",
                str(self.script),
                "install",
                "--skill-path",
                str(self.skills),
                "--local-only",
                "--json",
            ],
            self.repo,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertTrue(result["ok"])
        self.assertTrue((self.repo / ".ai" / "patchbay.toml").exists())
        self.assertTrue((self.skills / "patchbay" / "SKILL.md").exists())
        action_ids = {item["id"] for item in result["actions"]}
        doctor_action_ids = {item["id"] for item in result["doctor"]["actions"]}
        self.assertNotIn("probe_mcp", action_ids)
        self.assertNotIn("probe_mcp", doctor_action_ids)

    def test_cli_config_profile_apply_economy_routes_write_and_fix(self) -> None:
        from scripts.ai_flow.config import load_config, resolve_phase

        completed = run(
            [
                "python",
                str(self.script),
                "config",
                "profile",
                "apply",
                "economy",
                "--json",
            ],
            self.repo,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(result["profile"], "economy")
        self.assertEqual(result["status"]["profile"], "economy")
        actions = {item["id"]: item for item in result["actions"]}
        self.assertEqual(actions["open_readiness"]["message"], "readiness")
        self.assertEqual(actions["configure_reasonix_command"]["kind"], "local_agent")
        self.assertEqual(actions["configure_reasonix_command"]["message"], "configure reasonix command")
        self.assertIn("commands.reasonix", actions["configure_reasonix_command"]["command"])
        self.assertNotIn("start_new_task", actions)
        self.assertEqual(actions["validate_config"]["kind"], "command")
        cfg = load_config(self.repo)
        write = resolve_phase(cfg, "write")
        fix = resolve_phase(cfg, "fix")
        self.assertEqual(write["provider"], "reasonix_cli")
        self.assertEqual(write["model"], "deepseek-v4-pro")
        self.assertEqual(fix["provider"], "reasonix_cli")
        self.assertEqual(fix["model"], "deepseek-v4-pro")

    def test_doctor_recommends_economy_profile_for_custom_writer_route(self) -> None:
        from scripts.ai_flow.doctor import run_doctor

        ai_dir = self.repo / ".ai"
        ai_dir.mkdir()
        (ai_dir / "patchbay.toml").write_text(
            """
[phases.write]
provider = "mock"
model = "mock"

[phases.fix]
provider = "mock"
model = "mock"
""".lstrip(),
            encoding="utf-8",
        )

        result = run_doctor(self.repo, include_mcp=False, skill_path=self.skills)

        self.assertTrue(any("config profile apply economy" in item for item in result["recommendations"]))
        action = next(item for item in result["actions"] if item["id"] == "apply_economy_profile")
        self.assertEqual(action["kind"], "local_agent")
        self.assertEqual(action["message"], "apply economy profile")
        self.assertTrue(action["safe"])

    def test_doctor_exposes_structured_setup_and_skill_actions(self) -> None:
        from scripts.ai_flow.doctor import run_doctor

        result = run_doctor(self.repo, include_mcp=False, skill_path=self.skills)

        actions = {item["id"]: item for item in result["actions"]}
        self.assertIn("run_setup", actions)
        self.assertEqual(actions["run_setup"]["message"], "patchbay setup")
        self.assertIn("install_skill", actions)
        self.assertEqual(actions["install_skill"]["kind"], "local_agent")
        self.assertEqual(actions["install_skill"]["message"], "install Codex Skill")
        self.assertEqual(actions["install_skill"]["command"], "patchbay skill install codex")
        self.assertIn("probe_mcp", actions)
        self.assertEqual(actions["probe_mcp"]["command"], "patchbay doctor --host codex --probe-mcp --json")
        self.assertEqual(actions["probe_mcp"]["host"], "codex")

    def test_setup_omits_manual_mcp_step_after_successful_registration(self) -> None:
        from scripts.ai_flow import setup_flow

        mcp_result = {
            "host": "codex",
            "command": "codex mcp add patchbay -- python scripts/patchbay_mcp_server.py",
            "executed": True,
            "exit_code": 0,
            "stdout": "",
            "stderr": "",
            "note": "MCP server registered successfully.",
        }
        with mock.patch.object(setup_flow, "run_mcp_install", return_value=mcp_result):
            result = setup_flow.run_setup(self.repo, skill_path=self.skills)

        self.assertIn("MCP server registered successfully.", result["next_actions"])
        self.assertFalse(any(str(item).startswith("Register the MCP server with:") for item in result["next_actions"]))

    def test_mcp_setup_and_install_tools_wrap_same_flow(self) -> None:
        from scripts.ai_flow import mcp_server

        original_root = mcp_server.ROOT
        try:
            mcp_server.ROOT = self.repo
            for index, name in enumerate(("patchbay_setup", "patchbay_install", "ai_flow_install"), start=1):
                skill_path = self.tmp / f"skills-{name}"
                response = mcp_server.handle(
                    {
                        "jsonrpc": "2.0",
                        "id": index,
                        "method": "tools/call",
                        "params": {
                            "name": name,
                            "arguments": {
                                "host": "gemini",
                                "skill_path": str(skill_path),
                                "skip_mcp": True,
                            },
                        },
                    }
                )

                payload = json.loads(response["result"]["content"][0]["text"])
                self.assertTrue(payload["ok"])
                self.assertEqual(payload["setup_host"], "gemini")
                self.assertTrue((skill_path / "patchbay" / "SKILL.md").exists())
                actions = {item["id"]: item for item in payload["actions"]}
                self.assertNotIn("probe_mcp", actions)
                self.assertNotIn("install_mcp", actions)
                self.assertNotIn("register_mcp", actions)
                self.assertFalse(any("probe-mcp" in item.lower() or "mcp install" in item.lower() for item in payload["next_actions"]))
        finally:
            mcp_server.ROOT = original_root

    def test_mcp_doctor_can_suppress_mcp_followup_actions(self) -> None:
        from scripts.ai_flow import mcp_server

        original_root = mcp_server.ROOT
        try:
            mcp_server.ROOT = self.repo
            response = mcp_server.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {
                        "name": "patchbay_doctor",
                        "arguments": {
                            "host": "Claude Desktop",
                            "skip_mcp": True,
                        },
                    },
                }
            )
        finally:
            mcp_server.ROOT = original_root

        payload = json.loads(response["result"]["content"][0]["text"])
        self.assertEqual(payload["host"], "claude-desktop")
        self.assertTrue(payload["checks"]["mcp"]["skipped"])
        action_ids = {item["id"] for item in payload["actions"]}
        self.assertNotIn("probe_mcp", action_ids)
        self.assertNotIn("install_mcp", action_ids)
        self.assertFalse(any("probe-mcp" in item.lower() or "mcp install" in item.lower() for item in payload["next_actions"]))

    def test_setup_exposes_register_mcp_action_when_auto_registration_is_not_run(self) -> None:
        from scripts.ai_flow import setup_flow

        mcp_result = {
            "host": "codex",
            "command": "codex mcp add patchbay -- python scripts/patchbay_mcp_server.py",
            "executed": False,
            "dry_run": False,
            "note": "Codex CLI unavailable.",
        }
        with mock.patch.object(setup_flow, "run_mcp_install", return_value=mcp_result):
            result = setup_flow.run_setup(self.repo, skill_path=self.skills)

        action = next(item for item in result["actions"] if item["id"] == "register_mcp")
        self.assertEqual(action["kind"], "command")
        self.assertEqual(action["command"], "codex mcp add patchbay -- python scripts/patchbay_mcp_server.py")
        self.assertTrue(action["safe"])
        self.assertTrue(any("Register the MCP server with:" in item for item in result["next_actions"]))

    def test_setup_normalizes_natural_host_names(self) -> None:
        from scripts.ai_flow import setup_flow

        mcp_result = {
            "host": "claude-desktop",
            "command": "claude mcp add patchbay -- python scripts/patchbay_mcp_server.py",
            "executed": False,
            "dry_run": False,
            "note": "Claude Desktop registration command.",
        }
        with mock.patch.object(setup_flow, "run_mcp_install", return_value=mcp_result) as install_mock:
            result = setup_flow.run_setup(self.repo, host=" Claude Desktop ", skill_path=self.skills)

        install_mock.assert_called_once()
        self.assertEqual(install_mock.call_args.args[1], "claude-desktop")
        self.assertEqual(result["setup_host"], "claude-desktop")
        self.assertEqual(result["doctor"]["host"], "claude-desktop")
        action = next(item for item in result["actions"] if item["id"] == "register_mcp")
        self.assertEqual(action["host"], "claude-desktop")

    def test_setup_doctor_actions_inherit_target_host(self) -> None:
        from scripts.ai_flow import doctor, setup_flow

        mcp_result = {
            "host": "claude-desktop",
            "command": "claude mcp add patchbay -- python scripts/patchbay_mcp_server.py",
            "executed": False,
            "dry_run": True,
            "note": "Dry run.",
        }
        with (
            mock.patch.object(setup_flow, "run_mcp_install", return_value=mcp_result),
            mock.patch.object(doctor, "run_mcp_doctor", return_value={"server_reachable": False, "required_tools_present": False}),
        ):
            result = setup_flow.run_setup(self.repo, host="claude-desktop", skip_skill=True, mcp_dry_run=True, probe_mcp=True)

        actions = {item["id"]: item for item in result["actions"]}
        self.assertEqual(actions["install_mcp"]["command"], "patchbay mcp install claude-desktop")
        self.assertEqual(actions["install_mcp"]["host"], "claude-desktop")
        self.assertEqual(actions["refresh_readiness"]["host"], "claude-desktop")

    def test_mcp_skill_tools_install_and_verify_bundle(self) -> None:
        from scripts.ai_flow import mcp_server

        original_root = mcp_server.ROOT
        skill_path = self.tmp / "mcp-skill-root"
        try:
            mcp_server.ROOT = self.repo
            before_response = mcp_server.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {
                        "name": "patchbay_skill_doctor",
                        "arguments": {"skill_path": str(skill_path)},
                    },
                }
            )
            install_response = mcp_server.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "patchbay_skill_install",
                        "arguments": {"skill_path": str(skill_path)},
                    },
                }
            )
            after_response = mcp_server.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "patchbay_skill_doctor",
                        "arguments": {"skill_path": str(skill_path)},
                    },
                }
            )
        finally:
            mcp_server.ROOT = original_root

        before = json.loads(before_response["result"]["content"][0]["text"])
        installed = json.loads(install_response["result"]["content"][0]["text"])
        after = json.loads(after_response["result"]["content"][0]["text"])
        self.assertFalse(before["ready"])
        self.assertTrue(installed["installed"])
        self.assertTrue(after["ready"])
        self.assertTrue((skill_path / "patchbay" / "SKILL.md").exists())

    def test_mcp_config_profile_apply_economy(self) -> None:
        from scripts.ai_flow import mcp_server
        from scripts.ai_flow.config import load_config, resolve_phase

        original_root = mcp_server.ROOT
        try:
            mcp_server.ROOT = self.repo
            response = mcp_server.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {
                        "name": "patchbay_config_profile_apply",
                        "arguments": {"profile": "economy"},
                    },
                }
            )
        finally:
            mcp_server.ROOT = original_root

        payload = json.loads(response["result"]["content"][0]["text"])
        self.assertEqual(payload["profile"], "economy")
        actions = {item["id"]: item for item in payload["actions"]}
        self.assertEqual(actions["open_readiness"]["message"], "readiness")
        self.assertEqual(actions["configure_reasonix_command"]["kind"], "local_agent")
        self.assertEqual(actions["configure_reasonix_command"]["message"], "configure reasonix command")
        self.assertIn("commands.reasonix", actions["configure_reasonix_command"]["command"])
        self.assertNotIn("start_new_task", actions)
        cfg = load_config(self.repo)
        self.assertEqual(resolve_phase(cfg, "write")["model"], "deepseek-v4-pro")
        self.assertEqual(resolve_phase(cfg, "fix")["provider"], "reasonix_cli")


if __name__ == "__main__":
    unittest.main()
