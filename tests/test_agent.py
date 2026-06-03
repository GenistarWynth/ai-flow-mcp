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


def _timeout_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def run(
    command: list[str],
    cwd: Path,
    *,
    env: dict[str, str] | None = None,
    timeout: float = 60.0,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        stderr = _timeout_output(exc.stderr)
        message = f"Timed out after {timeout:g} seconds while running: {' '.join(command)}"
        if stderr:
            message = f"{message}\n{stderr}"
        return subprocess.CompletedProcess(
            command,
            124,
            stdout=_timeout_output(exc.stdout),
            stderr=message,
        )


class AgentTestCase(unittest.TestCase):
    _template_root: Path | None = None
    _template_repo: Path | None = None

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls._template_root = Path(tempfile.mkdtemp(prefix="patchbay-agent-template-"))
        cls._template_repo = cls._template_root / "repo"
        cls._template_repo.mkdir()

        for command in (
            ["git", "init"],
            ["git", "config", "user.email", "patchbay@example.test"],
            ["git", "config", "user.name", "Patchbay tests"],
        ):
            completed = run(command, cls._template_repo)
            if completed.returncode != 0:
                raise RuntimeError(completed.stderr)
        (cls._template_repo / "README.md").write_text("# Agent Repo\n", encoding="utf-8")
        (cls._template_repo / ".gitignore").write_text(
            ".ai/runs/\n.ai/logs/\n.ai/worktrees/\n.ai/patchbay.toml\n.patchbay-worktrees/\n",
            encoding="utf-8",
        )
        for command in (
            ["git", "add", "README.md", ".gitignore"],
            ["git", "commit", "-m", "initial"],
        ):
            completed = run(command, cls._template_repo)
            if completed.returncode != 0:
                raise RuntimeError(completed.stderr)

    @classmethod
    def tearDownClass(cls) -> None:
        if cls._template_root is not None:
            shutil.rmtree(cls._template_root, ignore_errors=True)
        cls._template_root = None
        cls._template_repo = None
        super().tearDownClass()

    def setUp(self) -> None:
        self.tempdir = Path(tempfile.mkdtemp(prefix="patchbay-agent-"))
        self.repo = self.tempdir / "repo"
        self.script = PROJECT_ROOT / "scripts" / "patchbay"
        if self._template_repo is None:
            self.fail("Agent test template repository was not initialized")
        shutil.copytree(self._template_repo, self.repo)
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
    def test_cli_helper_times_out_subprocesses_with_diagnostic(self) -> None:
        completed = run(
            [sys.executable, "-c", "import time; time.sleep(2)"],
            self.repo,
            timeout=0.1,
        )

        self.assertEqual(completed.returncode, 124)
        self.assertIn("Timed out after 0.1 seconds", completed.stderr)

    def test_agent_new_message_returns_plan_and_gate(self) -> None:
        response = agent_message(self.repo, "agent plans first")

        self.assertTrue(response["ok"])
        self.assertEqual(response["status"]["status"], "PLANNED")
        self.assertEqual(response["requires_confirmation"]["confirmation"], PLAN_CONFIRMATION)
        self.assertIn("PLAN.md", response["artifacts"])
        self.assertIn("Mock Implementation Plan", response["artifacts"]["PLAN.md"]["text"])
        self.assertEqual(response["context"]["next_actions"][0]["name"], "approve")
        self.assertIn("routing", response)
        self.assertFalse(response["routing"]["economy_configured"])
        self.assertEqual(response["routing"]["phases"]["write"]["configured"]["provider"], "mock")
        self.assertIn("Economy routing profile is not active", response["reply"])
        actions = {item["id"]: item for item in response["actions"]}
        self.assertEqual(actions["apply_economy_profile"]["message"], "apply economy profile")
        self.assertTrue(actions["apply_economy_profile"]["safe"])
        action_groups = {item["id"]: item for item in response["action_groups"]}
        self.assertIn("apply_economy_profile", action_groups["routing"]["action_ids"])
        self.assertFalse((self.repo / ".ai" / "runs" / response["run_id"] / "APPROVAL.json").exists())

    def test_agent_start_response_surfaces_economy_command_gap_before_approval(self) -> None:
        agent_message(self.repo, "apply economy profile")

        response = agent_message(self.repo, "agent plans with economy preview")

        self.assertEqual(response["action"], "start")
        self.assertEqual(response["status"]["status"], "PLANNED")
        self.assertTrue(response["routing"]["economy_configured"])
        self.assertFalse(response["routing"]["economy_command_ready"])
        self.assertEqual(response["routing"]["command_not_ready_phases"], ["write", "fix"])
        self.assertIn("cannot execute until `commands.reasonix`", response["reply"])
        actions = {item["id"]: item for item in response["actions"]}
        self.assertEqual(actions["configure_reasonix_command"]["message"], "configure reasonix command")
        self.assertTrue(actions["configure_reasonix_command"]["safe"])
        self.assertFalse((self.repo / ".ai" / "runs" / response["run_id"] / "APPROVAL.json").exists())

    def test_agent_doctor_message_returns_readiness_without_starting_run(self) -> None:
        response = agent_message(self.repo, "doctor")

        self.assertEqual(response["action"], "doctor")
        self.assertIn("doctor", response)
        self.assertIn("checks", response["doctor"])
        self.assertIn("routing", response)
        self.assertIn("routing", response["doctor"])
        self.assertEqual(response["routing"]["profile"], "custom")
        self.assertEqual(response["routing"]["workload_policy"]["economy_phases"], ["write", "fix"])
        self.assertEqual(response["doctor"]["routing"]["workload_policy"]["supervision_phases"], ["plan", "review"])
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
        self.assertIn("--probe-mcp", desktop_actions["probe_mcp"]["command"])
        self.assertEqual(gemini["setup_host"], "gemini")
        self.assertEqual(gemini["doctor"]["host"], "gemini")
        self.assertIsNone(desktop["run_id"])
        self.assertFalse((self.repo / ".ai" / "runs").exists())

    def test_agent_doctor_honors_mcp_avoidance_scope(self) -> None:
        response = agent_message(self.repo, "readiness for Claude Desktop without MCP")

        self.assertEqual(response["action"], "doctor")
        self.assertEqual(response["setup_host"], "claude-desktop")
        self.assertIsNone(response["run_id"])
        action_ids = {item["id"] for item in response["actions"]}
        doctor_action_ids = {item["id"] for item in response["doctor"]["actions"]}
        for blocked in ("probe_mcp", "install_mcp", "register_mcp"):
            self.assertNotIn(blocked, action_ids)
            self.assertNotIn(blocked, doctor_action_ids)
        self.assertFalse(any("probe-mcp" in item.lower() or "mcp install" in item.lower() for item in response["next_actions"]))
        self.assertFalse(any("probe-mcp" in item.lower() or "mcp install" in item.lower() for item in response["doctor"]["next_actions"]))
        self.assertFalse((self.repo / ".ai" / "runs").exists())

    def test_agent_doctor_surfaces_non_blocking_recommendations(self) -> None:
        response = agent_message(self.repo, "readiness")

        self.assertEqual(response["action"], "doctor")
        self.assertTrue(any("config profile apply economy" in item for item in response["recommendations"]))
        self.assertIn("apply economy profile", response["next_actions"])
        self.assertTrue(any(action["id"] == "apply_economy_profile" for action in response["actions"]))
        self.assertIn("Recommendations:", response["reply"])

    def test_agent_doctor_ready_state_promotes_safe_followups(self) -> None:
        from scripts.ai_flow import agent

        doctor_actions = [
            {
                "id": "start_new_task",
                "label": "Start new task",
                "kind": "focus_composer",
                "safe": True,
                "reason": "Readiness is healthy; focus the composer to start a gated Patchbay plan.",
            },
            {
                "id": "show_runs",
                "label": "Show runs",
                "kind": "local_agent",
                "message": "status",
                "safe": True,
                "reason": "List recent Patchbay runs without advancing any gate.",
            },
        ]
        doctor_actions.append(dict(doctor_actions[-1]))
        with mock.patch.object(
            agent,
            "run_doctor",
            return_value={
                "ok": True,
                "host": "codex",
                "checks": {},
                "next_actions": [],
                "recommendations": [],
                "actions": doctor_actions,
                "routing": {"economy_command_ready": True},
            },
        ):
            response = agent_message(self.repo, "readiness")

        self.assertEqual(response["action"], "doctor")
        self.assertEqual(response["next_actions"], ["start", "status"])
        self.assertEqual([item["id"] for item in response["actions"]], ["start_new_task", "show_runs"])
        actions = {item["id"]: item for item in response["actions"]}
        self.assertEqual(actions["start_new_task"]["kind"], "focus_composer")
        self.assertEqual(actions["show_runs"]["message"], "status")
        action_groups = {item["id"]: item for item in response["action_groups"]}
        self.assertIn("start_new_task", action_groups["new_task"]["action_ids"])
        self.assertIn("show_runs", action_groups["local"]["action_ids"])

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
        self.assertEqual(actions["configure_deepseek_provider"]["kind"], "local_agent")
        self.assertEqual(actions["configure_deepseek_provider"]["message"], "configure DeepSeek provider")
        self.assertNotIn("apply_economy_profile", actions)

    def test_agent_doctor_points_custom_provider_command_gaps_to_provider_command_action(self) -> None:
        agent_message(self.repo, "configure DeepSeek provider to definitely-missing-cheap-writer")

        response = agent_message(self.repo, "readiness")

        self.assertEqual(response["action"], "doctor")
        self.assertTrue(any("providers.cheap_writer.command" in item for item in response["recommendations"]))
        self.assertIn("configure economy provider command", response["next_actions"])
        actions = {item["id"]: item for item in response["actions"]}
        self.assertEqual(actions["configure_economy_provider_command"]["kind"], "command")
        self.assertEqual(
            actions["configure_economy_provider_command"]["command"],
            "patchbay config --set-key providers.cheap_writer.command --set-value <command>",
        )

    def test_agent_can_show_and_apply_economy_profile_without_starting_run(self) -> None:
        from scripts.ai_flow.config import load_config, resolve_phase

        shown = agent_message(self.repo, "show economy profile")
        self.assertEqual(shown["action"], "profile_show")
        self.assertEqual(shown["profile"]["profile"], "custom")
        self.assertFalse(shown["routing"]["economy_configured"])
        self.assertEqual(shown["routing"]["phases"]["write"]["configured"]["provider"], "mock")
        self.assertEqual(shown["routing"]["workload_policy"]["economy_phases"], ["write", "fix"])
        self.assertEqual(shown["routing"]["workload_policy"]["supervision_phases"], ["plan", "review"])
        self.assertIn("simple", shown["routing"]["workload_policy"]["summary"].lower())
        self.assertIn("low-cost", shown["routing"]["workload_policy"]["summary"].lower())
        self.assertIn("config profile apply economy", shown["reply"])
        self.assertIn("write/fix", shown["reply"])
        self.assertIn("low-cost", shown["reply"])
        self.assertIn("plan/review", shown["reply"])
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
        self.assertEqual(applied["routing"]["workload_policy"]["target_label"], "Reasonix/DeepSeek")
        self.assertEqual(applied["routing"]["workload_policy"]["phase_roles"]["write"], "economy")
        self.assertEqual(applied["routing"]["workload_policy"]["phase_roles"]["review"], "supervision")
        self.assertIn("write/fix", applied["reply"])
        self.assertIn("plan/review", applied["reply"])
        self.assertEqual(applied["routing"]["phases"]["write"]["command_status"]["status"], "missing_config")
        self.assertIn("commands.reasonix", applied["reply"])
        self.assertEqual(applied["routing"]["command_not_ready_phases"], ["write", "fix"])
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

        shown_ready_gap = agent_message(self.repo, "is writer using cheap model?")
        self.assertEqual(shown_ready_gap["action"], "profile_show")
        self.assertTrue(shown_ready_gap["routing"]["economy_configured"])
        self.assertFalse(shown_ready_gap["routing"]["economy_command_ready"])
        self.assertEqual(shown_ready_gap["routing"]["command_not_ready_phases"], ["write", "fix"])
        self.assertIn("cannot execute until `commands.reasonix`", shown_ready_gap["reply"])

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
        from scripts.ai_flow.events import append_event

        planned = agent_message(self.repo, "build routing question target")
        run_id = planned["run_id"]
        run_path = self.repo / ".ai" / "runs" / run_id
        append_event(
            run_path,
            phase="write",
            provider="mock",
            model="mock-model",
            action="success",
            status="IMPLEMENTED",
            detail="synthetic writer event",
            duration_ms=900,
            token_usage={"input_tokens": 150, "output_tokens": 50, "cached_tokens": 0, "total_tokens": 200},
            cost={"currency": "USD", "estimated_total": 0.02},
        )

        response = agent_message(self.repo, "is writer using cheap model?", run_id=run_id)

        self.assertEqual(response["action"], "profile_show")
        self.assertEqual(response["run_id"], run_id)
        self.assertEqual(response["metrics"]["run_id"], run_id)
        self.assertEqual(response["efficiency_summary"]["status"], "not_configured")
        self.assertIn("Run evidence:", response["reply"])
        cfg = load_config(self.repo)
        self.assertEqual(resolve_phase(cfg, "write")["provider"], "mock")
        self.assertFalse((self.repo / ".ai" / "runs" / run_id / "APPROVAL.json").exists())

    def test_agent_applies_economy_profile_from_cost_effective_writer_instruction(self) -> None:
        from scripts.ai_flow.config import load_config, resolve_phase

        for message in (
            "DeepSeek for simple writer work",
            "像写手这样的大量简单工作让便宜的模型比如 DeepSeek 去干",
            "优化成本，让写手工作走低价模型",
            "降本：把简单实现和修复切到低价模型",
            "把写手工作切到成本更低的模型",
            "写手工作走便宜模型，规划和审查用强模型",
        ):
            with self.subTest(message=message):
                response = agent_message(self.repo, message)

                self.assertEqual(response["action"], "profile_apply")
                self.assertIsNone(response["run_id"])
                self.assertTrue(response["routing"]["economy_configured"])
                self.assertEqual(response["routing"]["phases"]["write"]["configured"]["model"], "deepseek-v4-pro")
        cfg = load_config(self.repo)
        self.assertEqual(resolve_phase(cfg, "write")["provider"], "reasonix_cli")
        self.assertEqual(resolve_phase(cfg, "fix")["model"], "deepseek-v4-pro")
        self.assertFalse((self.repo / ".ai" / "runs").exists())

    def test_agent_custom_economy_provider_setup_returns_safe_command_without_mutating_config(self) -> None:
        from scripts.ai_flow.config import load_config, resolve_phase

        response = agent_message(self.repo, "configure DeepSeek provider for cheap writer work")

        self.assertEqual(response["action"], "custom_provider_setup")
        self.assertIsNone(response["run_id"])
        actions = {item["id"]: item for item in response["actions"]}
        command_action = actions["configure_custom_economy_provider"]
        self.assertEqual(command_action["kind"], "command")
        self.assertTrue(command_action["safe"])
        self.assertIn("config provider add-cli cheap_writer", command_action["command"])
        self.assertIn("--activate-economy", command_action["command"])
        self.assertIn("<deepseek-writer-command>", command_action["command"])
        self.assertEqual(response["custom_provider"]["roles"], ["write", "fix"])
        self.assertIn("readiness", response["next_actions"])

        cfg = load_config(self.repo)
        self.assertEqual(resolve_phase(cfg, "write")["provider"], "mock")
        self.assertEqual(resolve_phase(cfg, "fix")["provider"], "mock")
        self.assertFalse((self.repo / ".ai" / "runs").exists())

    def test_agent_custom_economy_provider_setup_with_explicit_command_configures_profile(self) -> None:
        from scripts.ai_flow.config import load_config, resolve_phase

        raw_command = sys.executable
        expected_command = f'"{raw_command}"' if " " in raw_command else raw_command
        response = agent_message(self.repo, f'configure DeepSeek provider to "{raw_command}"')

        self.assertEqual(response["action"], "custom_provider_configure")
        self.assertIsNone(response["run_id"])
        self.assertTrue(response["routing"]["economy_configured"])
        self.assertTrue(response["routing"]["economy_command_ready"])
        self.assertEqual(response["custom_provider"]["command"], expected_command)
        self.assertEqual(response["config_update"]["provider"], "cheap_writer")
        self.assertEqual(response["config_update"]["updated"]["command"], expected_command)
        actions = {item["id"]: item for item in response["actions"]}
        self.assertEqual(actions["start_new_task"]["kind"], "focus_composer")
        self.assertEqual(actions["validate_config"]["command"], "patchbay config --doctor --json")

        cfg = load_config(self.repo)
        self.assertEqual(cfg["providers"]["cheap_writer"]["command"], expected_command)
        self.assertEqual(resolve_phase(cfg, "write")["provider"], "cheap_writer")
        self.assertEqual(resolve_phase(cfg, "write")["model"], "deepseek-chat")
        self.assertEqual(resolve_phase(cfg, "fix")["provider"], "cheap_writer")
        self.assertFalse((self.repo / ".ai" / "runs").exists())

    def test_agent_custom_economy_provider_setup_with_missing_command_points_to_provider_command(self) -> None:
        response = agent_message(self.repo, "configure DeepSeek provider to definitely-missing-cheap-writer")

        self.assertEqual(response["action"], "custom_provider_configure")
        self.assertFalse(response["routing"]["economy_command_ready"])
        self.assertEqual(response["routing"]["command_not_ready_phases"], ["write", "fix"])
        self.assertIn("providers.cheap_writer.command", response["reply"])
        self.assertNotIn("commands.reasonix", response["reply"])
        self.assertIn("copy provider command", response["next_actions"])
        self.assertIn("inspect economy provider command", response["next_actions"])
        actions = {item["id"]: item for item in response["actions"]}
        self.assertEqual(actions["inspect_economy_provider_command"]["kind"], "local_agent")
        self.assertEqual(
            actions["configure_economy_provider_command"]["command"],
            "patchbay config --set-key providers.cheap_writer.command --set-value <command>",
        )
        self.assertNotIn("configure_reasonix_command", actions)
        self.assertFalse((self.repo / ".ai" / "runs").exists())

        shown = agent_message(self.repo, "show economy profile")
        self.assertEqual(shown["action"], "profile_show")
        self.assertIn("providers.cheap_writer.command", shown["reply"])
        self.assertNotIn("commands.reasonix", shown["reply"])
        shown_actions = {item["id"]: item for item in shown["actions"]}
        self.assertEqual(
            shown_actions["configure_economy_provider_command"]["command"],
            "patchbay config --set-key providers.cheap_writer.command --set-value <command>",
        )

    def test_agent_provider_command_question_is_read_only_profile(self) -> None:
        from scripts.ai_flow.config import load_config

        agent_message(self.repo, "configure DeepSeek provider to definitely-missing-cheap-writer")
        response = agent_message(self.repo, "why is providers.cheap_writer.command missing")

        self.assertEqual(response["action"], "profile_show")
        self.assertIsNone(response["run_id"])
        self.assertIn("providers.cheap_writer.command", response["reply"])
        self.assertEqual(load_config(self.repo)["providers"]["cheap_writer"]["command"], "definitely-missing-cheap-writer")
        self.assertFalse((self.repo / ".ai" / "runs").exists())

    def test_agent_can_repair_custom_provider_command_without_starting_run(self) -> None:
        from scripts.ai_flow.config import load_config, resolve_phase

        agent_message(self.repo, "configure DeepSeek provider to definitely-missing-cheap-writer")
        raw_command = sys.executable
        expected_command = f'"{raw_command}"' if " " in raw_command else raw_command
        response = agent_message(self.repo, f'configure cheap_writer command to "{raw_command}"')

        self.assertEqual(response["action"], "custom_provider_command_configure")
        self.assertIsNone(response["run_id"])
        self.assertEqual(response["config_update"]["set"]["providers.cheap_writer.command"], expected_command)
        self.assertEqual(response["custom_provider"]["source"], "providers.cheap_writer.command")
        self.assertTrue(response["routing"]["economy_command_ready"])
        actions = {item["id"]: item for item in response["actions"]}
        self.assertNotIn("configure_economy_provider_command", actions)

        cfg = load_config(self.repo)
        self.assertEqual(cfg["providers"]["cheap_writer"]["command"], expected_command)
        self.assertEqual(resolve_phase(cfg, "write")["provider"], "cheap_writer")
        self.assertFalse((self.repo / ".ai" / "runs").exists())

    def test_agent_accepts_provider_command_copy_action_as_conversation(self) -> None:
        from scripts.ai_flow.config import load_config

        agent_message(self.repo, "configure DeepSeek provider to definitely-missing-cheap-writer")
        raw_command = sys.executable
        expected_command = f'"{raw_command}"' if " " in raw_command else raw_command
        response = agent_message(
            self.repo,
            f'patchbay config --set-key providers.cheap_writer.command --set-value "{raw_command}"',
        )

        self.assertEqual(response["action"], "custom_provider_command_configure")
        self.assertEqual(response["config_update"]["set"]["providers.cheap_writer.command"], expected_command)
        self.assertEqual(load_config(self.repo)["providers"]["cheap_writer"]["command"], expected_command)
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

        chinese_cost_dashboard_task = agent_message(self.repo, "优化成本仪表盘")
        self.assertEqual(chinese_cost_dashboard_task["action"], "start")
        self.assertEqual(chinese_cost_dashboard_task["status"]["status"], "PLANNED")

    def test_agent_reasonix_command_words_in_chinese_task_still_start_plan(self) -> None:
        response = agent_message(self.repo, "使用 Reasonix 命令修复 writer 流程")

        self.assertEqual(response["action"], "start")
        self.assertEqual(response["status"]["status"], "PLANNED")

    def test_agent_unattended_word_in_task_still_starts_plan(self) -> None:
        response = agent_message(self.repo, "build unattended worker mode")

        self.assertEqual(response["action"], "start")
        self.assertEqual(response["status"]["status"], "PLANNED")

    def test_agent_help_message_returns_capabilities_without_starting_run(self) -> None:
        response = agent_message(self.repo, "help")

        self.assertEqual(response["action"], "help")
        self.assertIsNone(response["run_id"])
        self.assertIn("capabilities", response)
        self.assertIn("setup", response["next_actions"])
        self.assertIn("setup without MCP", response["next_actions"])
        self.assertIn("local mode", response["next_actions"])
        self.assertIn("readiness", response["next_actions"])
        self.assertIn("install Codex Skill", response["next_actions"])
        self.assertIn("skill doctor", response["next_actions"])
        self.assertIn("print Skill contract", response["next_actions"])
        self.assertIn("register MCP for Claude Desktop", response["next_actions"])
        setup_capability = next(item for item in response["capabilities"] if item["name"] == "setup")
        self.assertIn("Claude Desktop", setup_capability["summary"])
        self.assertIn("Gemini CLI", setup_capability["summary"])
        self.assertIn("patchbay setup without MCP", setup_capability["summary"])
        self.assertIn("install Codex Skill", setup_capability["summary"])
        self.assertIn("register MCP for Claude Desktop", setup_capability["summary"])
        self.assertIn("use Chrome Skill instead of MCP", setup_capability["summary"])
        self.assertIn("少用这个MCP", setup_capability["summary"])
        self.assertIn("不要用这个MCP", setup_capability["summary"])
        self.assertIn("不走 MCP", setup_capability["summary"])
        self.assertIn("走本地模式", setup_capability["summary"])
        self.assertIn("只用本地工具", setup_capability["summary"])
        self.assertIn("recommendations", setup_capability["summary"])
        self.assertIn("actions[]", setup_capability["summary"])
        self.assertIn("action_groups[]", setup_capability["summary"])
        custom_capability = next(item for item in response["capabilities"] if item["name"] == "custom-economy-provider")
        self.assertIn("configure DeepSeek provider to <command>", custom_capability["summary"])
        self.assertIn("configure economy provider command to <path>", custom_capability["summary"])
        self.assertIn("简单 writer/fix 用 DeepSeek 省钱", custom_capability["summary"])
        self.assertIn("降本，让简单 writer/fix 走低价模型", custom_capability["summary"])
        self.assertIn("configure_economy_provider_command", custom_capability["summary"])
        unattended_capability = next(item for item in response["capabilities"] if item["name"] == "unattended-approval")
        self.assertIn("run_id", unattended_capability["summary"])
        self.assertIn("full access", unattended_capability["summary"])
        self.assertIn("无需向我确认", unattended_capability["summary"])
        self.assertIn("apply_approved", unattended_capability["summary"])
        contract_capability = next(item for item in response["capabilities"] if item["name"] == "agent-skill-contract")
        contract = contract_capability["contract"]
        self.assertEqual(contract["kind"], "progressive-skill")
        self.assertEqual(contract["entrypoint"], "skills/patchbay/SKILL.md")
        self.assertTrue(contract["local_only_supported"])
        self.assertIn("patchbay skill doctor codex --json", contract["commands"])
        self.assertIn("actions[]", contract["structured_fields"])
        self.assertIn("failure_recovery", contract["structured_fields"])
        self.assertIn("不要用这个MCP", contract["no_mcp_prompts"])
        references = {item["path"]: item for item in contract["references"]}
        self.assertIn("skills/patchbay/references/install.md", references)
        self.assertIn("skills/patchbay/references/agent-contract.md", references)
        self.assertIn("action_groups", references["skills/patchbay/references/agent-contract.md"]["purpose"])
        actions = {item["id"]: item for item in response["actions"]}
        self.assertEqual(actions["run_setup"]["kind"], "local_agent")
        self.assertEqual(actions["run_setup"]["message"], "patchbay setup")
        self.assertEqual(actions["run_setup"]["host"], "codex")
        self.assertEqual(actions["run_local_setup"]["message"], "patchbay setup without MCP")
        self.assertEqual(actions["run_local_setup"]["host"], "codex")
        self.assertEqual(actions["use_local_mode"]["kind"], "local_agent")
        self.assertEqual(actions["use_local_mode"]["message"], "走本地模式，不走 MCP")
        self.assertEqual(actions["use_local_mode"]["host"], "codex")
        self.assertEqual(actions["install_skill_only"]["message"], "install Codex Skill")
        self.assertEqual(actions["install_skill_only"]["host"], "codex")
        self.assertEqual(actions["check_skill_contract"]["kind"], "command")
        self.assertEqual(actions["check_skill_contract"]["command"], "patchbay skill doctor codex --json")
        self.assertEqual(actions["print_skill_contract"]["command"], "patchbay skill print codex")
        self.assertEqual(actions["setup_claude_code"]["message"], "patchbay setup for claude-code")
        self.assertEqual(actions["setup_claude_code"]["host"], "claude-code")
        self.assertEqual(actions["setup_claude_desktop"]["message"], "patchbay setup for claude-desktop")
        self.assertEqual(actions["setup_claude_desktop"]["host"], "claude-desktop")
        self.assertEqual(actions["register_mcp_claude_desktop"]["message"], "register MCP for Claude Desktop")
        self.assertEqual(actions["register_mcp_claude_desktop"]["host"], "claude-desktop")
        self.assertEqual(actions["setup_gemini"]["message"], "install patchbay for gemini")
        self.assertEqual(actions["setup_gemini"]["host"], "gemini")
        self.assertEqual(actions["start_new_task"]["kind"], "focus_composer")
        self.assertEqual(actions["open_readiness"]["message"], "readiness")
        self.assertEqual(actions["open_readiness"]["host"], "codex")
        self.assertEqual(actions["readiness_claude_code"]["message"], "readiness for claude-code")
        self.assertEqual(actions["readiness_claude_code"]["host"], "claude-code")
        self.assertEqual(actions["readiness_claude_desktop"]["message"], "readiness for claude-desktop")
        self.assertEqual(actions["readiness_claude_desktop"]["host"], "claude-desktop")
        self.assertEqual(actions["readiness_gemini"]["message"], "readiness for gemini")
        self.assertEqual(actions["readiness_gemini"]["host"], "gemini")
        self.assertEqual(actions["configure_deepseek_provider"]["kind"], "local_agent")
        self.assertEqual(actions["configure_deepseek_provider"]["message"], "configure DeepSeek provider")
        self.assertEqual(actions["configure_custom_economy_provider"]["kind"], "command")
        self.assertIn("--activate-economy", actions["configure_custom_economy_provider"]["command"])
        self.assertEqual(actions["apply_economy_profile"]["message"], "apply economy profile")
        self.assertEqual(actions["configure_reasonix_command"]["message"], "configure reasonix command")
        self.assertIn("commands.reasonix", actions["configure_reasonix_command"]["command"])
        self.assertEqual(actions["show_runs"]["message"], "status")
        action_groups = {item["id"]: item for item in response["action_groups"]}
        self.assertIn("use_local_mode", action_groups["setup"]["action_ids"])
        self.assertIn("check_skill_contract", action_groups["setup"]["action_ids"])
        self.assertIn("print_skill_contract", action_groups["setup"]["action_ids"])
        self.assertIn("show_runs", action_groups["local"]["action_ids"])
        self.assertNotIn("background_polling", action_groups)
        self.assertTrue(all(item["safe"] for item in actions.values()))
        self.assertFalse((self.repo / ".ai" / "runs").exists())

    def test_agent_help_with_selected_run_returns_gate_context_without_advancing(self) -> None:
        planned = agent_message(self.repo, "build selected run help context")
        run_id = planned["run_id"]

        response = agent_message(self.repo, "help", run_id=run_id)

        self.assertEqual(response["action"], "help")
        self.assertEqual(response["run_id"], run_id)
        self.assertEqual(response["status"]["status"], "PLANNED")
        self.assertEqual(response["requires_confirmation"]["confirmation"], PLAN_CONFIRMATION)
        self.assertIn("capabilities", response)
        self.assertEqual(response["gate_diagnosis"]["status"], "PLANNED")
        self.assertEqual(response["gate_diagnosis"]["next_action"]["id"], "approve_and_run")
        self.assertFalse(response["gate_diagnosis"]["next_action"]["safe"])
        self.assertEqual(response["next_action"]["id"], "approve_and_run")
        self.assertFalse(response["next_action"]["safe"])
        self.assertIn("approve_and_run", response["next_actions"])
        self.assertIn("setup without MCP", response["next_actions"])
        actions = {item["id"]: item for item in response["actions"]}
        self.assertEqual(actions["open_plan"]["tab"], "Artifacts")
        self.assertEqual(actions["open_trace"]["tab"], "Trace")
        self.assertEqual(actions["run_local_setup"]["message"], "patchbay setup without MCP")
        self.assertEqual(actions["apply_economy_profile"]["message"], "apply economy profile")
        action_groups = {item["id"]: item for item in response["action_groups"]}
        self.assertIn("open_plan", action_groups["diagnostics"]["action_ids"])
        self.assertIn("run_local_setup", action_groups["setup"]["action_ids"])
        self.assertIn("apply_economy_profile", action_groups["routing"]["action_ids"])
        self.assertFalse((self.repo / ".ai" / "runs" / run_id / "APPROVAL.json").exists())

    def test_agent_failure_recovery_fallback_groups_actions(self) -> None:
        from scripts.ai_flow import agent

        recovery = agent._failure_recovery_summary({"status": "FAILED", "current_phase": "write"})

        groups = {item["id"]: item for item in recovery["action_groups"]}
        self.assertIn("inspect_events", groups["diagnostics"]["action_ids"])
        self.assertIn("inspect_artifacts", groups["diagnostics"]["action_ids"])
        self.assertIn("start_new_task", groups["new_task"]["action_ids"])

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
        self.assertIn("routing", response)
        self.assertEqual(response["routing"], response["setup"]["routing"])
        self.assertEqual(response["routing"]["workload_policy"]["economy_phases"], ["write", "fix"])
        self.assertTrue(any("config profile apply economy" in item for item in response["recommendations"]))
        self.assertIn("apply economy profile", response["next_actions"])
        self.assertIn("Recommendations:", response["reply"])
        self.assertIn("config profile apply economy", response["reply"])
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

    def test_agent_setup_scopes_skill_and_mcp_only_requests(self) -> None:
        import scripts.ai_flow.agent as agent_module

        calls: list[dict[str, object]] = []

        def fake_setup(
            root: Path,
            *,
            host: str = "codex",
            skip_mcp: bool = False,
            skip_skill: bool = False,
            **_: object,
        ) -> dict[str, object]:
            calls.append({"host": host, "skip_mcp": skip_mcp, "skip_skill": skip_skill})
            return {
                "ok": True,
                "root": str(root),
                "setup_host": host,
                "skill": {"skipped": skip_skill},
                "mcp": {"skipped": skip_mcp, "host": host},
                "doctor": {"ok": True},
                "next_actions": ["readiness", "start"],
                "actions": [],
            }

        with mock.patch.object(agent_module, "run_setup", side_effect=fake_setup):
            skill_only = agent_message(self.repo, "install Codex Skill")
            mcp_only = agent_message(self.repo, "register MCP for Claude Desktop")
            no_mcp = agent_message(self.repo, "patchbay setup without MCP")
            english_avoid_mcp = agent_message(self.repo, "please don't use MCP")
            zh_avoid_mcp = agent_message(self.repo, "不要用这个MCP好不好")
            zh_no_mcp = agent_message(self.repo, "patchbay setup 不要注册 MCP")

        self.assertEqual(
            calls,
            [
                {"host": "codex", "skip_mcp": True, "skip_skill": False},
                {"host": "claude-desktop", "skip_mcp": False, "skip_skill": True},
                {"host": "codex", "skip_mcp": True, "skip_skill": False},
                {"host": "codex", "skip_mcp": True, "skip_skill": False},
            ],
        )
        self.assertEqual(skill_only["setup"]["mcp"]["skipped"], True)
        self.assertEqual(mcp_only["setup"]["skill"]["skipped"], True)
        self.assertEqual(no_mcp["setup"]["mcp"]["skipped"], True)
        self.assertEqual(english_avoid_mcp["action"], "local_mode")
        self.assertTrue(english_avoid_mcp["local_mode"]["skip_mcp"])
        self.assertEqual(zh_avoid_mcp["action"], "local_mode")
        self.assertTrue(zh_avoid_mcp["local_mode"]["skip_mcp"])
        self.assertEqual(zh_no_mcp["setup"]["mcp"]["skipped"], True)
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
        self.assertEqual(response["runs"]["inbox"]["focus_run_id"], planned["run_id"])
        self.assertEqual(response["runs"]["inbox"]["confirmation_required_count"], 1)
        latest = response["runs"]["runs"][0]
        self.assertEqual(latest["run_id"], planned["run_id"])
        self.assertEqual(latest["inbox"]["key"], "needs_approval")
        self.assertEqual(latest["inbox"]["next_action"]["id"], "approve_and_run")
        self.assertFalse(latest["inbox"]["next_action"]["safe"])
        self.assertEqual(latest["inbox"]["next_action"]["requires_confirmation"]["confirmation"], PLAN_CONFIRMATION)
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
        self.assertEqual(response["run_reference"]["next_action"]["id"], "approve_and_run")
        self.assertFalse(response["run_reference"]["next_action"]["safe"])
        self.assertEqual(response["run_reference"]["next_action"]["requires_confirmation"]["confirmation"], PLAN_CONFIRMATION)
        self.assertEqual(response["next_action"]["id"], "open_latest_run")
        self.assertTrue(response["next_action"]["safe"])
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
                self.assertEqual(response["next_action"]["id"], "approve_and_run")
                self.assertFalse(response["next_action"]["safe"])
                self.assertEqual(response["next_action"]["requires_confirmation"]["confirmation"], PLAN_CONFIRMATION)
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
        self.assertEqual(response["gate_diagnosis"]["next_action"]["id"], "approve_and_run")
        self.assertFalse(response["gate_diagnosis"]["next_action"]["safe"])
        self.assertEqual(response["gate_diagnosis"]["next_action"]["requires_confirmation"]["confirmation"], PLAN_CONFIRMATION)
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
        self.assertEqual(response["run_reference"]["gate_diagnosis"]["next_action"]["id"], "approve_and_run")
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
        self.assertEqual(response["gate_diagnosis"]["next_action"]["id"], "apply")
        self.assertFalse(response["gate_diagnosis"]["next_action"]["safe"])
        self.assertEqual(response["gate_diagnosis"]["next_action"]["requires_confirmation"]["confirmation"], APPLY_CONFIRMATION)
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

    def test_agent_metrics_without_run_reads_latest_run(self) -> None:
        planned = agent_message(self.repo, "build latest run target")

        response = agent_message(self.repo, "metrics")

        self.assertEqual(response["action"], "metrics")
        self.assertTrue(response["ok"])
        self.assertEqual(response["run_id"], planned["run_id"])
        self.assertEqual(response["metrics"]["run_id"], planned["run_id"])
        self.assertEqual(response["recent_run"]["run_id"], planned["run_id"])
        self.assertEqual(response["run_reference"]["run_id"], planned["run_id"])
        self.assertEqual(response["requested_view"]["tab"], "Overview")
        self.assertIn("Latest run", response["reply"])
        actions = {item["id"]: item for item in response["actions"]}
        self.assertEqual(actions["open_latest_run"]["run_id"], planned["run_id"])
        action_groups = {item["id"]: item for item in response["action_groups"]}
        self.assertIn("open_latest_run", action_groups["diagnostics"]["action_ids"])
        self.assertIn("apply_economy_profile", action_groups["routing"]["action_ids"])
        self.assertEqual(len(list((self.repo / ".ai" / "runs").iterdir())), 1)

    def test_agent_metrics_with_run_returns_efficiency_digest(self) -> None:
        planned = agent_message(self.repo, "metrics target")

        response = agent_message(self.repo, "metrics", run_id=planned["run_id"])

        self.assertEqual(response["action"], "metrics")
        self.assertTrue(response["ok"])
        self.assertEqual(response["run_id"], planned["run_id"])
        self.assertEqual(response["metrics"]["run_id"], planned["run_id"])
        self.assertIn("run_metrics", response["metrics"])
        self.assertIn("phase attempt", response["reply"])
        action_groups = {item["id"]: item for item in response["action_groups"]}
        self.assertIn("apply_economy_profile", action_groups["routing"]["action_ids"])

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
        recovery_groups = {item["id"]: item for item in response["recovery"]["action_groups"]}
        self.assertIn("inspect_events", recovery_groups["diagnostics"]["action_ids"])
        self.assertIn("start_new_task", recovery_groups["new_task"]["action_ids"])
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

    def test_agent_view_prompts_without_run_read_latest_run(self) -> None:
        planned = agent_message(self.repo, "latest view handoff")
        run_id = planned["run_id"]

        cases = [
            ("context", "Overview", "context"),
            ("poll context", "Overview", "context"),
            ("handoff context", "Overview", "context"),
            ("diff", "Diff", "diff"),
            ("events", "Trace", "events"),
            ("poll events", "Trace", "events"),
            ("logs", "Log", "artifact"),
            ("artifact", "Artifacts", "artifact"),
            ("看补丁", "Diff", "diff"),
            ("查看事件轨迹", "Trace", "events"),
            ("打开日志", "Log", "artifact"),
            ("看计划产物", "Artifacts", "artifact"),
            ("查看失败原因", "Log", "artifact"),
            ("为什么失败", "Log", "artifact"),
            ("why did it fail", "Log", "artifact"),
        ]
        for message, tab, action in cases:
            with self.subTest(message=message):
                response = agent_message(self.repo, message)
                self.assertEqual(response["action"], action)
                self.assertEqual(response["run_id"], run_id)
                self.assertEqual(response["recent_run"]["run_id"], run_id)
                self.assertEqual(response["run_reference"]["requested_view"]["tab"], tab)
                self.assertEqual(response["requested_view"]["tab"], tab)
                actions = {item["id"]: item for item in response["actions"]}
                self.assertEqual(actions["open_latest_run"]["run_id"], run_id)
                self.assertEqual(actions["open_latest_run"]["tab"], tab)
                action_groups = {item["id"]: item for item in response["action_groups"]}
                self.assertIn("open_latest_run", action_groups["diagnostics"]["action_ids"])
                self.assertFalse((self.repo / ".ai" / "runs" / run_id / "APPROVAL.json").exists())

    def test_agent_view_prompt_without_runs_returns_local_guidance(self) -> None:
        response = agent_message(self.repo, "diff")

        self.assertEqual(response["action"], "missing_run")
        self.assertFalse(response["ok"])
        self.assertIsNone(response["run_id"])
        self.assertIsNone(response["run_reference"])
        self.assertEqual(response["requested_view"]["tab"], "Diff")

    def test_agent_response_reuses_loaded_status_for_context(self) -> None:
        planned = agent_message(self.repo, "status reuse target")
        run_id = planned["run_id"]

        from scripts.ai_flow import service

        with mock.patch.object(service, "status", wraps=service.status) as status_mock:
            response = agent_message(self.repo, "context", run_id=run_id)

        self.assertEqual(response["action"], "context")
        self.assertEqual(response["run_id"], run_id)
        self.assertEqual(status_mock.call_count, 1)

    def test_agent_run_bound_view_prompts_return_diagnostic_actions(self) -> None:
        planned = agent_message(self.repo, "selected run diagnostics")
        run_id = planned["run_id"]

        cases = [
            ("context", "Overview", "context"),
            ("poll context", "Overview", "context"),
            ("diff", "Diff", "diff"),
            ("events", "Trace", "events"),
            ("poll events", "Trace", "events"),
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

        for message in ("继续推进", "确认计划", "应用补丁"):
            with self.subTest(message=message):
                response = agent_message(self.repo, message)
                self.assertEqual(response["action"], "missing_run")
                self.assertEqual(response["recent_run"]["run_id"], run_id)
                self.assertEqual(response["run_reference"]["run_id"], run_id)
                self.assertIn("open latest run", response["next_actions"])
        metrics = agent_message(self.repo, "查看成本")
        self.assertEqual(metrics["action"], "metrics")
        self.assertEqual(metrics["run_id"], run_id)
        self.assertEqual(metrics["recent_run"]["run_id"], run_id)

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

    def test_agent_approval_blocks_missing_reasonix_without_failing_run(self) -> None:
        agent_message(self.repo, "apply economy profile")
        planned = agent_message(self.repo, "ready for economy autopilot")

        response = agent_message(self.repo, "approve", run_id=planned["run_id"], confirmation=PLAN_CONFIRMATION)

        self.assertFalse(response["ok"])
        self.assertEqual(response["status"]["status"], "APPROVED")
        self.assertEqual(response["autopilot"]["blocker"]["phase"], "write")
        self.assertIn("commands.reasonix", response["error"])
        self.assertIn("configure reasonix command", response["next_actions"])
        self.assertFalse((self.repo / ".ai" / "runs" / planned["run_id"] / "WORKTREE_PATH").exists())

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
        self.assertFalse(response["gate_diagnosis"]["ready_to_apply"])
        self.assertEqual(response["gate_diagnosis"]["next_action"]["id"], "approve_and_run")
        self.assertEqual(response["gate_diagnosis"]["next_action"]["requires_confirmation"]["confirmation"], PLAN_CONFIRMATION)
        blocker_keys = [item["key"] for item in response["gate_diagnosis"]["blockers"]]
        self.assertIn("approval", blocker_keys)
        self.assertIn("tests", blocker_keys)
        self.assertIn("review", blocker_keys)
        actions = {item["id"]: item for item in response["actions"]}
        self.assertEqual(actions["open_plan"]["tab"], "Artifacts")
        self.assertEqual(actions["open_trace"]["tab"], "Trace")
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
        self.assertFalse(apply_response["gate_diagnosis"]["ready_to_apply"])
        self.assertIn("tests", [item["key"] for item in apply_response["gate_diagnosis"]["blockers"]])
        self.assertEqual(apply_response["gate_diagnosis"]["next_action"]["id"], "open_readiness")
        self.assertEqual(apply_response["gate_diagnosis"]["next_action"]["message"], "readiness")
        self.assertEqual({item["id"]: item for item in apply_response["actions"]}["open_diff"]["tab"], "Diff")

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

    def test_mcp_patchbay_agent_can_return_custom_provider_setup_command(self) -> None:
        from scripts.ai_flow import mcp_server

        original_root = mcp_server.ROOT
        try:
            mcp_server.ROOT = self.repo
            response = mcp_server.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": "patchbay_agent", "arguments": {"message": "configure DeepSeek provider"}},
                }
            )
        finally:
            mcp_server.ROOT = original_root

        payload = json.loads(response["result"]["content"][0]["text"])
        self.assertEqual(payload["action"], "custom_provider_setup")
        actions = {item["id"]: item for item in payload["actions"]}
        self.assertIn("--activate-economy", actions["configure_custom_economy_provider"]["command"])
        self.assertIsNone(payload["run_id"])

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
        self.assertEqual(payload["run_reference"]["next_action"]["id"], "approve_and_run")
        self.assertFalse(payload["run_reference"]["next_action"]["safe"])
        self.assertEqual(payload["run_reference"]["next_action"]["requires_confirmation"]["confirmation"], PLAN_CONFIRMATION)
        self.assertEqual(payload["next_action"]["id"], "open_latest_run")
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
            command_key="reasonix",
            action="success",
            status="IMPLEMENTED",
            detail="synthetic economy writer event",
            duration_ms=1200,
            token_usage={"input_tokens": 500, "output_tokens": 200, "cached_tokens": 0, "total_tokens": 700},
            cost={"currency": "USD", "estimated_total": 0.01},
        )

        response = agent_message(self.repo, "cost", run_id=planned["run_id"])

        routing = response["metrics"]["routing_evidence"]
        efficiency = response["metrics"]["efficiency_summary"]
        tier_usage = response["metrics"]["run_metrics"]["tier_usage"]
        self.assertEqual(tier_usage["economy"]["token_usage"]["total_tokens"], 700)
        self.assertEqual(efficiency["status"], "pending_evidence")
        self.assertEqual(efficiency["economy_share"]["total_tokens"], 700)
        self.assertEqual(efficiency["economy_share"]["token_percent"], 100.0)
        self.assertIn("1/2 economy phases observed", efficiency["summary"])
        self.assertIn("economy tier 100.0% tokens", response["reply"])
        self.assertIn("efficiency pending_evidence", response["reply"])
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

    def test_agent_metrics_flags_command_key_drift_on_economy_route(self) -> None:
        from scripts.ai_flow.events import append_event

        agent_message(self.repo, "apply economy profile")
        self._set_reasonix_command_to_python()
        planned = agent_message(self.repo, "command key routing drift target")
        run_path = self.repo / ".ai" / "runs" / planned["run_id"]
        append_event(
            run_path,
            phase="write",
            provider="reasonix_cli",
            model="deepseek-v4-pro",
            command_key="other_reasonix",
            action="success",
            status="IMPLEMENTED",
            detail="synthetic writer event through the wrong command alias",
            duration_ms=1200,
        )

        response = agent_message(self.repo, "cost", run_id=planned["run_id"])

        routing = response["metrics"]["routing_evidence"]
        self.assertTrue(routing["economy_configured"])
        self.assertEqual(routing["observed_economy_phases"], [])
        self.assertEqual(routing["observed_non_economy_phases"], ["write"])
        self.assertEqual(routing["phases"]["write"]["observed"][0]["command_key"], "other_reasonix")
        self.assertEqual(routing["phases"]["write"]["status"], "observed_other")
        self.assertEqual(routing["economy_health"]["status"], "drift")
        self.assertEqual(routing["actions"][0]["id"], "inspect_routing_events")

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
            command_key="reasonix",
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

    def test_agent_metrics_uses_custom_economy_target_for_observed_routes(self) -> None:
        from scripts.ai_flow.events import append_event

        config_path = self.repo / ".ai" / "patchbay.toml"
        with config_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(
                """

[profiles.economy]
provider = "mock"
model = "mock"
label = "Mock writer"
"""
            )
        planned = agent_message(self.repo, "build custom target fixture")
        run_path = self.repo / ".ai" / "runs" / planned["run_id"]
        append_event(
            run_path,
            phase="write",
            provider="mock",
            model="mock",
            action="success",
            status="IMPLEMENTED",
            detail="synthetic custom economy writer event",
            duration_ms=1200,
        )
        append_event(
            run_path,
            phase="write",
            provider="reasonix_cli",
            model="deepseek-v4-pro",
            action="retry",
            status="IMPLEMENTED",
            detail="synthetic default route drift",
            duration_ms=800,
        )

        response = agent_message(self.repo, "cost", run_id=planned["run_id"])

        routing = response["metrics"]["routing_evidence"]
        self.assertEqual(routing["target"]["provider"], "mock")
        self.assertEqual(routing["target"]["label"], "Mock writer")
        self.assertTrue(routing["economy_configured"])
        self.assertIsNone(routing["economy_command_ready"])
        self.assertEqual(routing["phases"]["write"]["status"], "observed_mixed")
        self.assertEqual(routing["observed_economy_phases"], ["write"])
        self.assertEqual(routing["observed_non_economy_phases"], ["write"])
        self.assertEqual(routing["economy_health"]["status"], "drift")
        self.assertEqual(routing["phases"]["write"]["observed"][0]["provider"], "mock")
        self.assertEqual(routing["phases"]["write"]["observed"][1]["provider"], "reasonix_cli")

    def test_agent_metrics_warns_when_custom_economy_provider_command_is_missing(self) -> None:
        config_path = self.repo / ".ai" / "patchbay.toml"
        config_path.write_text(
            """
[phases.plan]
provider = "mock"

[phases.review]
provider = "mock"

[workflow]
allow_apply_without_tests = true

[commands_allowlist]
test = []

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
        planned = agent_message(self.repo, "build custom command health fixture")

        response = agent_message(self.repo, "cost", run_id=planned["run_id"])

        routing = response["metrics"]["routing_evidence"]
        self.assertTrue(routing["economy_configured"])
        self.assertFalse(routing["economy_command_ready"])
        self.assertEqual(routing["command_not_ready_phases"], ["write", "fix"])
        self.assertEqual(routing["economy_health"]["next_action"], "inspect_economy_provider_command")
        self.assertEqual(routing["actions"][0]["id"], "configure_economy_provider_command")
        self.assertEqual(routing["actions"][1]["id"], "inspect_economy_provider_command")
        self.assertEqual(routing["phases"]["write"]["command_status"]["source"], "providers.cheap_writer.command")

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

    def test_cli_agent_mixed_language_deepseek_writer_prompts_apply_economy_profile(self) -> None:
        for message in (
            "简单 writer/fix 用 DeepSeek 省钱",
            "让 DeepSeek 处理简单 writer/fix",
            "simple writer fix use DeepSeek",
            "降本，让简单 writer/fix 走低价模型",
        ):
            with self.subTest(message=message):
                response = self.cli_json("agent", "message", message)

                self.assertEqual(response["action"], "profile_apply")
                self.assertEqual(response["profile"]["status"]["profile"], "economy")
                self.assertIsNone(response["run_id"])
        runs_path = self.repo / ".ai" / "runs"
        self.assertFalse(runs_path.exists() and any(runs_path.iterdir()))

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

    def test_cli_agent_configure_deepseek_provider_accepts_explicit_command(self) -> None:
        from scripts.ai_flow.config import load_config, resolve_phase

        raw_command = sys.executable
        expected_command = f'"{raw_command}"' if " " in raw_command else raw_command
        response = self.cli_json("agent", "message", f'configure DeepSeek provider to "{raw_command}"')

        self.assertEqual(response["action"], "custom_provider_configure")
        self.assertEqual(response["config_update"]["updated"]["command"], expected_command)
        self.assertTrue(response["routing"]["economy_configured"])
        self.assertIsNone(response["run_id"])
        cfg = load_config(self.repo)
        self.assertEqual(cfg["providers"]["cheap_writer"]["command"], expected_command)
        self.assertEqual(resolve_phase(cfg, "write")["provider"], "cheap_writer")

    def test_cli_agent_repairs_custom_provider_command(self) -> None:
        from scripts.ai_flow.config import load_config

        self.cli_json("agent", "message", "configure DeepSeek provider to definitely-missing-cheap-writer")
        raw_command = sys.executable
        expected_command = f'"{raw_command}"' if " " in raw_command else raw_command
        response = self.cli_json("agent", "message", f'configure economy provider command to "{raw_command}"')

        self.assertEqual(response["action"], "custom_provider_command_configure")
        self.assertEqual(response["config_update"]["set"]["providers.cheap_writer.command"], expected_command)
        self.assertTrue(response["routing"]["economy_command_ready"])
        self.assertEqual(load_config(self.repo)["providers"]["cheap_writer"]["command"], expected_command)
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

    def test_cli_agent_metrics_without_run_reads_latest_run(self) -> None:
        planned = agent_message(self.repo, "build cli latest run target")

        response = self.cli_json("agent", "message", "cost")

        self.assertEqual(response["action"], "metrics")
        self.assertEqual(response["run_id"], planned["run_id"])
        self.assertEqual(response["metrics"]["run_id"], planned["run_id"])
        self.assertEqual(response["recent_run"]["run_id"], planned["run_id"])

    def test_cli_agent_continue_without_run_returns_local_guidance(self) -> None:
        response = self.cli_json("agent", "message", "continue")

        self.assertEqual(response["action"], "missing_run")
        self.assertFalse(response["ok"])
        self.assertIsNone(response["run_id"])
        self.assertIsNone(response["run_reference"])

    def test_agent_background_start_returns_pollable_job(self) -> None:
        from scripts.ai_flow import service

        response = agent_message(self.repo, "background agent plan", background=True)
        run_id = response["run_id"]
        run_path = self.repo / ".ai" / "runs" / run_id

        self.assertTrue(response["ok"])
        self.assertTrue(response["background"])
        self.assertEqual(response["job"]["phase"], "plan")
        self.assertTrue(response["background_job"]["active"])
        self.assertEqual(response["background_job"]["status"], "running")
        self.assertEqual(response["background_job"]["phase"], "plan")
        self.assertEqual(response["next_actions"], ["status", "context", "events"])
        self.assertIn("routing", response)
        self.assertFalse(response["routing"]["economy_configured"])
        self.assertEqual(response["routing"]["phases"]["write"]["configured"]["provider"], "mock")
        actions = {item["id"]: item for item in response["actions"]}
        self.assertEqual(actions["open_background_run"]["kind"], "open_run")
        self.assertEqual(actions["open_background_run"]["run_id"], run_id)
        self.assertEqual(actions["open_trace"]["tab"], "Trace")
        self.assertEqual(actions["poll_status"]["message"], "status")
        self.assertEqual(actions["poll_context"]["message"], "context")
        self.assertEqual(actions["poll_events"]["message"], "events")
        self.assertEqual(actions["cancel_background_job"]["message"], "cancel background job")
        self.assertEqual(actions["apply_economy_profile"]["message"], "apply economy profile")
        self.assertTrue(all(item["safe"] for item in response["actions"]))
        action_groups = {item["id"]: item for item in response["action_groups"]}
        self.assertEqual(action_groups["background_polling"]["action_ids"], ["poll_status", "poll_context", "poll_events"])
        self.assertEqual(action_groups["background_control"]["action_ids"], ["cancel_background_job"])
        self.assertIn("open_background_run", action_groups["diagnostics"]["action_ids"])
        self.assertIn("apply_economy_profile", action_groups["routing"]["action_ids"])
        background_actions = {item["id"]: item for item in response["background_job"]["actions"]}
        self.assertEqual(background_actions["open_background_run"]["run_id"], run_id)
        self.assertEqual(background_actions["open_trace"]["tab"], "Trace")
        self.assertEqual(background_actions["poll_status"]["message"], "status")
        self.assertEqual(background_actions["poll_context"]["message"], "context")
        self.assertEqual(background_actions["poll_events"]["message"], "events")
        self.assertEqual(background_actions["cancel_background_job"]["message"], "cancel background job")
        self.assertNotIn("apply_economy_profile", background_actions)
        background_groups = {item["id"]: item for item in response["background_job"]["action_groups"]}
        self.assertEqual(background_groups["background_polling"]["action_ids"], ["poll_status", "poll_context", "poll_events"])
        self.assertEqual(background_groups["background_control"]["action_ids"], ["cancel_background_job"])
        self.assertNotIn("routing", background_groups)
        status_actions = {item["id"]: item for item in service.status(self.repo, run_id)["background_job"]["actions"]}
        self.assertEqual(status_actions["open_background_run"]["run_id"], run_id)
        self.assertEqual(status_actions["open_trace"]["tab"], "Trace")
        self.assertEqual(status_actions["cancel_background_job"]["run_id"], run_id)
        status_groups = {item["id"]: item for item in service.status(self.repo, run_id)["background_job"]["action_groups"]}
        self.assertIn("poll_context", status_groups["background_polling"]["action_ids"])
        self.assertEqual(status_groups["background_control"]["action_ids"], ["cancel_background_job"])
        job_actions = {item["id"]: item for item in json.loads((run_path / "JOB.json").read_text(encoding="utf-8"))["actions"]}
        self.assertEqual(job_actions["poll_status"]["message"], "status")
        self.assertEqual(job_actions["poll_context"]["message"], "context")
        self.assertEqual(job_actions["poll_events"]["message"], "events")
        self.assertEqual(job_actions["cancel_background_job"]["message"], "cancel background job")
        self.assertNotIn("approve", {item.get("message") for item in response["actions"]})
        self.assertNotIn("apply", {item.get("message") for item in response["actions"]})
        self.assertNotIn("continue", {item.get("message") for item in response["actions"]})
        self.assertTrue((run_path / "JOB.json").exists())
        self.assertTrue((run_path / "events.jsonl").exists())

    def test_agent_can_cancel_active_background_job(self) -> None:
        from scripts.ai_flow import service

        planned = agent_message(self.repo, "prepare active background control workflow")
        run_id = planned["run_id"]
        run_path = self.repo / ".ai" / "runs" / run_id
        (run_path / "AGENT.lock").write_text("agent\ncancel-token\n", encoding="utf-8")
        service._record_job(
            run_path,
            {
                "background": True,
                "kind": "agent",
                "phase": "agent",
                "action": "continue",
                "pid": 12345,
                "run_id": run_id,
                "started_at": "2026-06-03T00:00:00+00:00",
                "started_at_epoch": 0,
                "actions": service.background_followup_actions(run_id),
            },
        )

        with mock.patch.object(service, "_terminate_background_process", return_value={"attempted": True, "terminated": True}) as terminate:
            response = agent_message(self.repo, "stop background job", run_id=run_id)

        terminate.assert_called_once_with(12345)
        self.assertEqual(response["action"], "background_cancel")
        self.assertTrue(response["ok"])
        self.assertTrue(response["canceled"])
        self.assertEqual(response["background_job"]["status"], "canceled")
        self.assertFalse(response["background_job"]["active"])
        self.assertFalse((run_path / "AGENT.lock").exists())
        status = service.status(self.repo, run_id)
        self.assertEqual(status["status"], "FAILED")
        self.assertEqual(status["background_job"]["status"], "canceled")
        self.assertIn("Background job canceled", status["error"])

    def test_agent_background_approval_requires_confirmation(self) -> None:
        planned = agent_message(self.repo, "background approval still gated")

        response = agent_message(self.repo, "approve", run_id=planned["run_id"], background=True)

        self.assertEqual(response["status"]["status"], "PLANNED")
        self.assertEqual(response["requires_confirmation"]["confirmation"], PLAN_CONFIRMATION)
        self.assertFalse((self.repo / ".ai" / "runs" / planned["run_id"] / "AGENT.lock").exists())

    def test_agent_unattended_permission_approves_plan_for_selected_run(self) -> None:
        for index, message in enumerate(
            (
                "don't ask me, you have all permissions",
                "full access, approve yourself",
                "无需向我确认，继续",
                "我给你完全访问权限了，不要问我了",
                "别找我呀，自己允许",
            )
        ):
            with self.subTest(message=message):
                planned = agent_message(self.repo, f"plan permission target {index}")

                response = agent_message(
                    self.repo,
                    message,
                    run_id=planned["run_id"],
                )

                self.assertEqual(response["action"], "approve_and_run")
                self.assertEqual(response["confirmation_source"], "message")
                self.assertEqual(response["status"]["status"], "REVIEWED_PASS")
                self.assertEqual(response["requires_confirmation"]["confirmation"], APPLY_CONFIRMATION)
                self.assertTrue((self.repo / ".ai" / "runs" / planned["run_id"] / "APPROVAL.json").exists())

    def test_agent_no_mcp_preference_with_selected_run_uses_local_mode(self) -> None:
        from scripts.ai_flow import service

        planned = agent_message(self.repo, "selected run local mode target")
        run_id = planned["run_id"]

        for message in (
            "please don't use MCP",
            "no MCP",
            "不要用这个MCP好不好",
            "能不能少用这个MCP，用自带浏览器功能",
            "use Chrome Skill instead of MCP",
            "走本地模式，不走 MCP",
            "只用本地工具，不走 MCP",
        ):
            with self.subTest(message=message):
                response = agent_message(self.repo, message, run_id=run_id)

                self.assertEqual(response["action"], "local_mode")
                self.assertTrue(response["ok"])
                self.assertEqual(response["run_id"], run_id)
                self.assertTrue(response["local_mode"]["skip_mcp"])
                self.assertEqual(service.status(self.repo, run_id)["status"], "PLANNED")

    def test_agent_unattended_permission_without_run_does_not_start_task(self) -> None:
        for message in (
            "don't ask me, you have all permissions",
            "full access, approve yourself",
            "\u4e0d\u8981\u95ee\u6211\u4e86\uff0c\u6240\u6709\u6743\u9650\u90fd\u7ed9\u4f60",
            "\u65e0\u9700\u5411\u6211\u786e\u8ba4\uff0c\u6240\u6709\u6743\u9650\u5168\u90e8\u7ed9\u4f60",
        ):
            with self.subTest(message=message):
                response = agent_message(self.repo, message)

                self.assertEqual(response["action"], "missing_run")
                self.assertFalse(response["ok"])
                self.assertIsNone(response["run_id"])
        runs_path = self.repo / ".ai" / "runs"
        self.assertFalse(runs_path.exists() and any(runs_path.iterdir()))

    def test_agent_tool_preference_without_run_uses_local_mode_not_start(self) -> None:
        for message in (
            "能不能少用这个MCP，用自带浏览器功能",
            "不要用这个MCP，你明明有Chrome Skill",
            "please use browser skill instead of MCP",
            "只用本地工具，不走 MCP",
            "走本地模式，不走 MCP",
        ):
            with self.subTest(message=message):
                response = agent_message(self.repo, message)

                self.assertEqual(response["action"], "local_mode")
                self.assertTrue(response["local_mode"]["skip_mcp"])
                self.assertIsNone(response["run_id"])
        runs_path = self.repo / ".ai" / "runs"
        self.assertFalse(runs_path.exists() and any(runs_path.iterdir()))

    def test_agent_background_unattended_permission_starts_agent_job(self) -> None:
        from scripts.ai_flow import agent as agent_module

        planned = agent_message(self.repo, "background permission target")
        run_id = planned["run_id"]
        run_path = self.repo / ".ai" / "runs" / run_id

        class FakeProcess:
            pid = 4321

            def poll(self):
                return None

        with (
            mock.patch.object(agent_module.service, "resolve_root", return_value=self.repo),
            mock.patch.object(agent_module.subprocess, "Popen", return_value=FakeProcess()),
        ):
            response = agent_message(
                self.repo,
                "do not ask me, assume yes",
                run_id=run_id,
                background=True,
            )

        self.assertTrue(response["background"])
        self.assertIsNone(response["requires_confirmation"])
        self.assertEqual(response["job"]["action"], "approve_and_run")
        self.assertTrue((run_path / "AGENT.lock").exists())

    def test_agent_background_continue_starts_agent_job(self) -> None:
        from scripts.ai_flow import agent as agent_module
        from scripts.ai_flow import service

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
        self.assertTrue(response["background_job"]["active"])
        self.assertEqual(response["background_job"]["kind"], "agent")
        self.assertEqual(response["background_job"]["pid"], 9876)
        actions = {item["id"]: item for item in response["actions"]}
        self.assertEqual(actions["open_background_run"]["kind"], "open_run")
        self.assertEqual(actions["open_background_run"]["run_id"], run_id)
        self.assertEqual(actions["open_trace"]["tab"], "Trace")
        self.assertEqual(actions["poll_status"]["message"], "status")
        self.assertEqual(actions["poll_context"]["message"], "context")
        self.assertEqual(actions["cancel_background_job"]["message"], "cancel background job")
        self.assertTrue(all(item["safe"] for item in response["actions"]))
        action_groups = {item["id"]: item for item in response["action_groups"]}
        self.assertEqual(action_groups["background_polling"]["action_ids"], ["poll_status", "poll_context", "poll_events"])
        self.assertEqual(action_groups["background_control"]["action_ids"], ["cancel_background_job"])
        self.assertIn("open_background_run", action_groups["diagnostics"]["action_ids"])
        background_actions = {item["id"]: item for item in response["background_job"]["actions"]}
        self.assertEqual(background_actions["open_background_run"]["run_id"], run_id)
        self.assertEqual(background_actions["open_trace"]["tab"], "Trace")
        self.assertEqual(background_actions["poll_status"]["message"], "status")
        self.assertEqual(background_actions["poll_context"]["message"], "context")
        self.assertEqual(background_actions["poll_events"]["message"], "events")
        self.assertEqual(background_actions["cancel_background_job"]["message"], "cancel background job")
        status_actions = {item["id"]: item for item in service.status(self.repo, run_id)["background_job"]["actions"]}
        self.assertEqual(status_actions["open_background_run"]["run_id"], run_id)
        self.assertEqual(status_actions["poll_context"]["message"], "context")
        self.assertEqual(status_actions["poll_events"]["message"], "events")
        self.assertEqual(status_actions["cancel_background_job"]["run_id"], run_id)
        job_actions = {item["id"]: item for item in json.loads((run_path / "JOB.json").read_text(encoding="utf-8"))["actions"]}
        self.assertEqual(job_actions["open_trace"]["tab"], "Trace")
        self.assertEqual(job_actions["poll_status"]["message"], "status")
        self.assertEqual(job_actions["poll_context"]["message"], "context")
        self.assertEqual(job_actions["cancel_background_job"]["message"], "cancel background job")
        self.assertNotIn("approve", {item.get("message") for item in response["actions"]})
        self.assertNotIn("apply", {item.get("message") for item in response["actions"]})
        self.assertNotIn("continue", {item.get("message") for item in response["actions"]})
        self.assertTrue((run_path / "AGENT.lock").exists())
        self.assertTrue((run_path / "JOB.json").exists())
        self.assertTrue(popen.call_args.kwargs["env"]["PATCHBAY_INHERITED_AGENT_LOCK"])

    def test_agent_background_continue_is_idempotent_while_active(self) -> None:
        from scripts.ai_flow import agent as agent_module

        planned = agent_message(self.repo, "background duplicate guard")
        run_id = planned["run_id"]

        class FakeProcess:
            pid = 9876

            def poll(self):
                return None

        with (
            mock.patch.object(agent_module.service, "resolve_root", return_value=self.repo),
            mock.patch.object(agent_module.subprocess, "Popen", return_value=FakeProcess()),
        ):
            first = agent_message(
                self.repo,
                "approve",
                run_id=run_id,
                confirmation=PLAN_CONFIRMATION,
                background=True,
            )

        self.assertTrue(first["background_job"]["active"])
        with (
            mock.patch.object(agent_module.service, "resolve_root", return_value=self.repo),
            mock.patch.object(agent_module.subprocess, "Popen", side_effect=AssertionError("duplicate background spawn")),
        ):
            second = agent_message(self.repo, "continue", run_id=run_id, background=True)

        self.assertTrue(second["ok"])
        self.assertTrue(second["background"])
        self.assertTrue(second["already_running"])
        self.assertIsNone(second["requires_confirmation"])
        self.assertEqual(second["next_actions"], ["status", "context", "events"])
        self.assertEqual(second["background_job"]["pid"], 9876)
        actions = {item["id"]: item for item in second["actions"]}
        self.assertEqual(actions["open_background_run"]["run_id"], run_id)
        self.assertEqual(actions["poll_context"]["message"], "context")
        self.assertNotIn("approve", {item.get("message") for item in second["actions"]})
        self.assertNotIn("apply", {item.get("message") for item in second["actions"]})
        self.assertNotIn("continue", {item.get("message") for item in second["actions"]})

    def test_cli_background_agent_approval_completes_in_child_process(self) -> None:
        from scripts.ai_flow import service

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
        def completed_job() -> dict | None:
            payload = json.loads((run_path / "JOB.json").read_text(encoding="utf-8"))
            return payload if "exit_code" in payload else None

        job = self.wait_for(completed_job)
        status_payload = service.status(self.repo, run_id)
        self.assertEqual(status["status"], "REVIEWED_PASS")
        self.assertEqual(job["exit_code"], 0)
        self.assertEqual(status_payload["background_job"]["status"], "finished")
        self.assertFalse(status_payload["background_job"]["active"])
        status_actions = {item["id"]: item for item in status_payload["background_job"]["actions"]}
        self.assertEqual(status_actions["open_background_run"]["run_id"], run_id)
        self.assertEqual(status_actions["poll_status"]["message"], "status")
        self.assertEqual(status_actions["poll_context"]["message"], "context")
        self.assertEqual(status_actions["poll_events"]["message"], "events")
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
