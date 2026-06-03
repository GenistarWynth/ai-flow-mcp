"""Tests for run listing, artifact reads, and background phase jobs."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str], cwd: Path, *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    child_env = os.environ.copy()
    if env:
        child_env.update(env)
    return subprocess.run(
        command,
        cwd=str(cwd),
        env=child_env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


class PublicVisibilityTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = Path(tempfile.mkdtemp(prefix="patchbay-visibility-"))
        self.repo = self.tempdir / "repo"
        self.repo.mkdir()
        run(["git", "init"], self.repo)
        run(["git", "config", "user.email", "patchbay@example.test"], self.repo)
        run(["git", "config", "user.name", "Patchbay tests"], self.repo)
        (self.repo / "README.md").write_text("# Visibility Repo\n", encoding="utf-8")
        (self.repo / ".gitignore").write_text(
            ".ai/runs/\n.ai/logs/\n.ai/worktrees/\n.ai/patchbay.toml\n.patchbay-worktrees/\n",
            encoding="utf-8",
        )
        run(["git", "add", "README.md", ".gitignore"], self.repo)
        run(["git", "commit", "-m", "initial"], self.repo)
        self.script = PROJECT_ROOT / "scripts" / "patchbay"

    def tearDown(self) -> None:
        shutil.rmtree(self.tempdir, ignore_errors=True)

    def cli_json(self, *args: str) -> dict:
        completed = run(["python", str(self.script), *args, "--json"], self.repo)
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

    def test_runs_lists_existing_runs(self) -> None:
        planned = self.cli_json("plan", "--task", "listable run", "--mock")

        result = self.cli_json("runs")
        runs_by_id = {item["run_id"]: item for item in result["runs"]}
        listed = runs_by_id[planned["run_id"]]
        actions = {item["id"]: item for item in listed["actions"]}
        groups = {item["key"]: item for item in result["inbox"]["groups"]}

        self.assertIn(planned["run_id"], runs_by_id)
        self.assertGreaterEqual(result["count"], 1)
        self.assertEqual(listed["current_phase"], "approve")
        self.assertEqual(listed["next_commands"], ["approve"])
        self.assertFalse(listed["gate_state"]["approved"])
        self.assertEqual(listed["inbox"]["key"], "needs_approval")
        self.assertEqual(listed["inbox"]["next_action"]["id"], "approve_and_run")
        self.assertFalse(listed["inbox"]["next_action"]["safe"])
        self.assertEqual(listed["inbox"]["next_action"]["requires_confirmation"]["confirmation"], "plan_approved")
        self.assertEqual(actions["open_run"]["kind"], "open_run")
        self.assertEqual(actions["approve_and_run"]["requires_confirmation"]["type"], "plan_approval")
        self.assertEqual(result["inbox"]["confirmation_required_count"], 1)
        self.assertEqual(result["inbox"]["focus_run_id"], planned["run_id"])
        self.assertIn("needs_approval", groups)
        self.assertIn(planned["run_id"], groups["needs_approval"]["run_ids"])

    def test_runs_text_views_surface_inbox_and_focus(self) -> None:
        planned = self.cli_json("plan", "--task", "cli inbox view", "--mock")

        full = run(["python", str(self.script), "runs"], self.repo)
        inbox = run(["python", str(self.script), "runs", "--inbox"], self.repo)
        focus = run(["python", str(self.script), "runs", "--focus"], self.repo)

        for completed in (full, inbox, focus):
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("Agent inbox:", completed.stdout)
            self.assertIn("Needs plan approval", completed.stdout)
            self.assertIn(planned["run_id"], completed.stdout)
            self.assertIn("Approve plan (confirmation:plan_approved)", completed.stdout)

        self.assertIn("Runs:", full.stdout)
        self.assertNotIn("Runs:", inbox.stdout)
        self.assertIn("Focus:", focus.stdout)
        self.assertIn("run_id:", focus.stdout)
        self.assertIn("title: cli inbox view", focus.stdout)
        self.assertIn("next_action: Approve plan (confirmation:plan_approved)", focus.stdout)

    def test_agent_runs_text_view_reuses_inbox_renderer(self) -> None:
        planned = self.cli_json("plan", "--task", "agent inbox view", "--mock")

        runs = run(["python", str(self.script), "agent", "message", "runs"], self.repo)
        status = run(["python", str(self.script), "agent", "message", "status"], self.repo)
        structured = self.cli_json("agent", "message", "runs")

        for completed in (runs, status):
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("Latest Patchbay run", completed.stdout)
            self.assertIn("Agent inbox:", completed.stdout)
            self.assertIn("Needs plan approval", completed.stdout)
            self.assertIn(planned["run_id"], completed.stdout)
            self.assertIn("Approve plan (confirmation:plan_approved)", completed.stdout)
            self.assertIn("Actions:", completed.stdout)
            self.assertNotIn("runs: {", completed.stdout)
            self.assertNotIn("actions: [{", completed.stdout)

        self.assertIn("runs", structured)
        self.assertIn(planned["run_id"], {item["run_id"] for item in structured["runs"]["runs"]})

    def test_readiness_text_views_summarize_checks_and_actions(self) -> None:
        doctor = run(["python", str(self.script), "doctor", "--local-only"], self.repo)
        readiness = run(["python", str(self.script), "agent", "message", "readiness without MCP"], self.repo)
        structured = self.cli_json("agent", "message", "readiness")

        for completed in (doctor, readiness):
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("Patchbay readiness:", completed.stdout)
            self.assertIn("Checks:", completed.stdout)
            self.assertIn("- repo:", completed.stdout)
            self.assertIn("Actions:", completed.stdout)
            self.assertNotIn("checks: {", completed.stdout)
            self.assertNotIn("actions: [{", completed.stdout)

        self.assertIn("doctor", structured)
        self.assertIn("checks", structured["doctor"])

    def test_setup_text_views_summarize_steps_and_readiness(self) -> None:
        direct = run(["python", str(self.script), "setup", "--host", "codex", "--no-mcp", "--dry-run"], self.repo)
        agent = run(
            ["python", str(self.script), "agent", "message", "patchbay setup without MCP"],
            self.repo,
            env={"CODEX_HOME": str(self.tempdir / "codex-home")},
        )
        structured = self.cli_json("setup", "--host", "codex", "--no-mcp", "--dry-run")

        for completed in (direct, agent):
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("Patchbay setup:", completed.stdout)
            self.assertIn("root:", completed.stdout)
            self.assertIn("config:", completed.stdout)
            self.assertIn("skill:", completed.stdout)
            self.assertIn("mcp: skipped", completed.stdout)
            self.assertIn("Patchbay readiness:", completed.stdout)
            self.assertIn("Actions:", completed.stdout)
            self.assertNotIn("setup: {", completed.stdout)
            self.assertNotIn("doctor: {", completed.stdout)

        self.assertIn("doctor", structured)
        self.assertIn("setup_host", structured)

    def test_profile_text_views_summarize_routing_and_actions(self) -> None:
        direct = run(["python", str(self.script), "config", "profile", "show"], self.repo)
        agent = run(["python", str(self.script), "agent", "message", "show economy profile"], self.repo)
        direct_apply = run(["python", str(self.script), "config", "profile", "apply", "economy"], self.repo)
        agent_apply = run(["python", str(self.script), "agent", "message", "apply economy profile"], self.repo)
        structured = self.cli_json("config", "profile", "show")

        for completed in (direct, agent, direct_apply, agent_apply):
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("Patchbay profile:", completed.stdout)
            self.assertIn("Phase routing:", completed.stdout)
            self.assertIn("- write:", completed.stdout)
            self.assertIn("- fix:", completed.stdout)
            self.assertIn("Actions:", completed.stdout)
            self.assertNotIn("economy: {", completed.stdout)
            self.assertNotIn("phase_strategy: {", completed.stdout)
            self.assertNotIn("actions: [{", completed.stdout)

        self.assertIn("phase_strategy", structured)
        self.assertIn("economy", structured)

    def test_metrics_text_views_summarize_efficiency_and_routing(self) -> None:
        from scripts.ai_flow.events import append_event

        run(["python", str(self.script), "config", "--set-key", "commands.reasonix", "--set-value", sys.executable], self.repo)
        planned = self.cli_json("plan", "--task", "metrics text view", "--mock")
        run_id = planned["run_id"]
        run_dir = self.repo / ".ai" / "runs" / run_id
        append_event(
            run_dir,
            phase="write",
            provider="reasonix_cli",
            model="deepseek-v4-pro",
            command_key="reasonix",
            action="success",
            status="IMPLEMENTED",
            run_id=run_id,
            duration_ms=2000,
            token_usage={"input_tokens": 450, "output_tokens": 150, "cached_tokens": 0, "total_tokens": 600},
            cost={"currency": "USD", "estimated_total": 0.03},
        )
        append_event(
            run_dir,
            phase="fix",
            provider="reasonix_cli",
            model="deepseek-v4-pro",
            command_key="reasonix",
            action="success",
            status="IMPLEMENTED",
            run_id=run_id,
            duration_ms=1000,
            token_usage={"input_tokens": 300, "output_tokens": 100, "cached_tokens": 0, "total_tokens": 400},
            cost={"currency": "USD", "estimated_total": 0.02},
        )
        append_event(
            run_dir,
            phase="review",
            provider="codex_cli",
            model="gpt-5",
            action="success",
            status="REVIEWED_PASS",
            run_id=run_id,
            duration_ms=1200,
            token_usage={"input_tokens": 800, "output_tokens": 200, "cached_tokens": 0, "total_tokens": 1000},
            cost={"currency": "USD", "estimated_total": 0.20},
        )

        direct = run(["python", str(self.script), "metrics", run_id], self.repo)
        agent = run(["python", str(self.script), "agent", "message", "metrics", "--run-id", run_id], self.repo)
        structured = self.cli_json("metrics", run_id)

        for completed in (direct, agent):
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("Patchbay metrics:", completed.stdout)
            self.assertIn(run_id, completed.stdout)
            self.assertIn("Efficiency:", completed.stdout)
            self.assertIn("Tier usage:", completed.stdout)
            self.assertIn("Economy write/fix", completed.stdout)
            self.assertIn("Provider usage:", completed.stdout)
            self.assertIn("write: reasonix_cli / deepseek-v4-pro", completed.stdout)
            self.assertNotIn("run_metrics: {", completed.stdout)
            self.assertNotIn("routing_evidence: {", completed.stdout)

        self.assertIn("run_metrics", structured)
        self.assertIn("efficiency_summary", structured)

    def test_agent_guidance_text_views_summarize_without_payload_dump(self) -> None:
        planned = self.cli_json("plan", "--task", "guidance text view", "--mock")

        help_view = run(["python", str(self.script), "agent", "message", "help"], self.repo)
        local_mode = run(["python", str(self.script), "agent", "message", "不要用这个MCP"], self.repo)
        next_step = run(["python", str(self.script), "agent", "message", "what should I do next"], self.repo)
        gate_status = run(
            ["python", str(self.script), "agent", "message", "why can't I apply", "--run-id", planned["run_id"]],
            self.repo,
        )
        structured = self.cli_json("agent", "message", "help")

        self.assertIn("Patchbay help:", help_view.stdout)
        self.assertIn("Capabilities:", help_view.stdout)
        self.assertIn("Patchbay local mode:", local_mode.stdout)
        self.assertIn("skip_mcp:", local_mode.stdout)
        self.assertIn("Patchbay next step:", next_step.stdout)
        self.assertIn("Agent inbox:", next_step.stdout)
        self.assertIn("Patchbay gate status:", gate_status.stdout)
        self.assertIn("Gate diagnosis:", gate_status.stdout)

        for completed in (help_view, local_mode, next_step, gate_status):
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertNotIn("capabilities: [{", completed.stdout)
            self.assertNotIn("local_mode: {", completed.stdout)
            self.assertNotIn("runs: {", completed.stdout)
            self.assertNotIn("gate_diagnosis: {", completed.stdout)
            self.assertNotIn("actions: [{", completed.stdout)

        self.assertIn("capabilities", structured)
        self.assertIn("actions", structured)

    def test_run_diagnostic_text_views_summarize_status_and_context(self) -> None:
        planned = self.cli_json("plan", "--task", "run diagnostic text view", "--mock")
        run_id = planned["run_id"]

        direct_status = run(["python", str(self.script), "status", run_id], self.repo)
        agent_status = run(["python", str(self.script), "agent", "message", "status", "--run-id", run_id], self.repo)
        direct_context = run(["python", str(self.script), "context", run_id], self.repo)
        agent_context = run(["python", str(self.script), "agent", "message", "context", "--run-id", run_id], self.repo)
        structured_status = self.cli_json("status", run_id)
        structured_context = self.cli_json("context", run_id)

        for completed in (direct_status, agent_status):
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("Patchbay status:", completed.stdout)
            self.assertIn("Gate state:", completed.stdout)
            self.assertIn("Run metrics:", completed.stdout)
            self.assertNotIn("gate_state: {", completed.stdout)
            self.assertNotIn("run_metrics: {", completed.stdout)
            self.assertNotIn("routing_evidence: {", completed.stdout)

        for completed in (direct_context, agent_context):
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("Patchbay context:", completed.stdout)
            self.assertIn("summary:", completed.stdout)
            self.assertIn("Agent activity:", completed.stdout)
            self.assertIn("Next actions:", completed.stdout)
            self.assertNotIn("agent_activity: {", completed.stdout)
            self.assertNotIn("timeline: [{", completed.stdout)
            self.assertNotIn("next_actions: [{", completed.stdout)

        self.assertIn("gate_state", structured_status)
        self.assertIn("agent_activity", structured_context)

    def test_diagnostic_view_text_views_summarize_events_trace_and_artifacts(self) -> None:
        planned = self.cli_json("plan", "--task", "diagnostic views text view", "--mock")
        run_id = planned["run_id"]

        events = run(["python", str(self.script), "events", run_id], self.repo)
        trace = run(["python", str(self.script), "trace", run_id], self.repo)
        artifact = run(["python", str(self.script), "artifact", run_id, "PLAN.md", "--tail", "3"], self.repo)
        agent_events = run(["python", str(self.script), "agent", "message", "events", "--run-id", run_id], self.repo)
        agent_logs = run(["python", str(self.script), "agent", "message", "logs", "--run-id", run_id], self.repo)
        structured = self.cli_json("events", run_id)

        self.assertIn("Patchbay events:", events.stdout)
        self.assertIn("Timeline:", events.stdout)
        self.assertIn("plan.start", events.stdout)
        self.assertIn("Patchbay trace:", trace.stdout)
        self.assertIn("No trace entries returned.", trace.stdout)
        self.assertIn("Patchbay artifact:", artifact.stdout)
        self.assertIn("PATCHBAY_MOCK_OUTPUT.md", artifact.stdout)
        self.assertIn("Patchbay events view:", agent_events.stdout)
        self.assertIn("Patchbay artifact view:", agent_logs.stdout)
        self.assertIn("requested_view: Log", agent_logs.stdout)

        for completed in (events, trace, artifact, agent_events, agent_logs):
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertNotIn("events: [{", completed.stdout)
            self.assertNotIn("trace: []", completed.stdout)
            self.assertNotIn("status: {", completed.stdout)
            self.assertNotIn("context: {", completed.stdout)
            self.assertNotIn("artifacts: {", completed.stdout)

        self.assertIn("events", structured)
        self.assertEqual(structured["run_id"], run_id)

    def test_artifact_reads_and_tails_run_file(self) -> None:
        planned = self.cli_json("plan", "--task", "artifact read", "--mock")

        full = self.cli_json("artifact", planned["run_id"], "TASK.md")
        tail = self.cli_json("artifact", planned["run_id"], "TASK.md", "--tail", "1")

        self.assertEqual(full["artifact"], "TASK.md")
        self.assertIn("artifact read", full["text"])
        self.assertEqual(tail["lines_returned"], 1)

    def test_artifact_rejects_path_traversal(self) -> None:
        planned = self.cli_json("plan", "--task", "bad artifact", "--mock")
        completed = run(
            ["python", str(self.script), "artifact", planned["run_id"], "../STATUS.json", "--json"],
            self.repo,
        )

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("artifact name", completed.stderr.lower())

    def test_mcp_tools_include_runs_artifact_and_background_schema(self) -> None:
        from scripts.ai_flow.mcp_server import handle

        response = handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        assert response is not None
        tools = {tool["name"]: tool for tool in response["result"]["tools"]}
        self.assertIn("patchbay_setup", tools)
        self.assertIn("patchbay_runs", tools)
        self.assertIn("patchbay_artifact", tools)
        self.assertIn("patchbay_cancel", tools)
        self.assertIn("patchbay_config_show", tools)
        self.assertIn("patchbay_config_phase_set", tools)
        self.assertIn("patchbay_config_command_set", tools)
        self.assertIn("patchbay_config_test_add", tools)
        self.assertIn("patchbay_config_provider_add_cli", tools)
        self.assertIn("background", tools["patchbay_plan"]["inputSchema"]["properties"])
        self.assertIn("background", tools["patchbay_write"]["inputSchema"]["properties"])
        self.assertIn("background", tools["patchbay_agent"]["inputSchema"]["properties"])
        self.assertIn("skill_path", tools["patchbay_setup"]["inputSchema"]["properties"])

    def test_chinese_readme_surfaces_custom_economy_provider_agent_prompts(self) -> None:
        text = (PROJECT_ROOT / "README.zh-CN.md").read_text(encoding="utf-8")

        self.assertIn("configure DeepSeek provider", text)
        self.assertIn("configure DeepSeek provider to <command>", text)
        self.assertIn("configure economy provider command to <path>", text)
        self.assertIn("configure_economy_provider_command", text)
        self.assertIn("providers.<id>.command", text)
        self.assertIn("降本，让简单 writer/fix 走低价模型", text)
        self.assertIn("capabilities[]", text)
        self.assertIn("Agent 能力面板", text)
        self.assertIn("gate_diagnosis.next_action", text)
        self.assertIn("无需向我确认", text)
        self.assertIn("完全访问权限", text)

    def test_english_readme_quickstart_surfaces_custom_economy_provider_agent_prompts(self) -> None:
        text = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn('patchbay agent message "configure DeepSeek provider" --json', text)
        self.assertIn('patchbay agent message "configure DeepSeek provider to <command>" --json', text)
        self.assertIn('patchbay agent message "configure economy provider command to <path>" --json', text)
        self.assertIn("降本，让简单 writer/fix 走低价模型", text)
        self.assertIn("Agent help surface", text)
        self.assertIn("capabilities[]", text)
        self.assertIn("selected-run `gate_diagnosis.next_action`", text)
        self.assertIn("full access", text)
        self.assertIn("approve yourself", text)

    def test_background_plan_returns_job_metadata(self) -> None:
        from scripts.ai_flow import service
        from scripts.ai_flow.mcp_server import patchbay_plan

        with mock.patch.object(service, "start_background_phase") as start:
            start.return_value = {
                "background": True,
                "phase": "plan",
                "pid": 123,
                "run_id": "20260524-background-task",
                "run_dir": str(self.repo / ".ai" / "runs" / "20260524-background-task"),
                "events_path": str(self.repo / ".ai" / "runs" / "20260524-background-task" / "events.jsonl"),
                "job": {"phase": "plan"},
            }

            result = patchbay_plan("background task", background=True)

        self.assertTrue(result["background"])
        self.assertEqual(result["phase"], "plan")
        self.assertEqual(result["pid"], 123)
        self.assertNotEqual(result["run_id"], "pending")
        self.assertTrue(result["events_path"].endswith("events.jsonl"))

    def test_background_plan_cli_returns_pollable_run_id(self) -> None:
        completed = run(
            ["python", str(self.script), "plan", "--task", "background pollable", "--mock", "--background", "--json"],
            self.repo,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)

        self.assertTrue(result["background"])
        self.assertNotEqual(result["run_id"], "pending")
        self.assertTrue(Path(result["run_dir"]).exists())
        self.assertTrue(Path(result["events_path"]).exists())

    def test_pending_background_plan_is_readable_before_status_exists(self) -> None:
        from scripts.ai_flow import service

        run_id = "20260524-pending-background"
        run_path = self.repo / ".ai" / "runs" / run_id
        run_path.mkdir(parents=True)
        (run_path / "JOB.json").write_text(
            json.dumps(
                {
                    "background": True,
                    "phase": "plan",
                    "pid": 123,
                    "run_id": run_id,
                    "task": "pending background task",
                    "started_at": "2026-05-24T00:00:00+00:00",
                    "started_at_epoch": 0,
                    "root": str(self.repo),
                    "run_dir": str(run_path),
                    "events_path": str(run_path / "events.jsonl"),
                    "trace_path": str(run_path / "trace.jsonl"),
                }
            ),
            encoding="utf-8",
        )
        (run_path / "events.jsonl").write_text("", encoding="utf-8")

        status = service.status(self.repo, run_id)
        context = service.context(self.repo, run_id)
        runs = service.runs(self.repo)

        self.assertEqual(status["status"], "RUNNING")
        self.assertEqual(status["job"]["pid"], 123)
        self.assertTrue(status["background_job"]["active"])
        self.assertEqual(status["background_job"]["status"], "running")
        self.assertEqual(status["background_job"]["phase"], "plan")
        self.assertEqual(status["background_job"]["pid"], 123)
        self.assertFalse(status["gate_state"]["approved"])
        self.assertEqual(context["status"], "RUNNING")
        self.assertTrue(context["background_job"]["active"])
        self.assertTrue(context["agent_activity"]["background_job"]["active"])
        listed = next(item for item in runs["runs"] if item["run_id"] == run_id)
        self.assertEqual(listed["task"], "pending background task")
        self.assertEqual(listed["background_job"]["status"], "running")

    def test_finished_background_job_without_status_is_reported_failed(self) -> None:
        from scripts.ai_flow import service

        run_id = "20260524-finished-background-without-status"
        run_path = self.repo / ".ai" / "runs" / run_id
        run_path.mkdir(parents=True)
        (run_path / "JOB.json").write_text(
            json.dumps(
                {
                    "background": True,
                    "phase": "plan",
                    "pid": 123,
                    "run_id": run_id,
                    "task": "finished background task",
                    "exit_code": 9,
                    "started_at": "2026-05-24T00:00:00+00:00",
                    "started_at_epoch": 0,
                    "finished_at": "2026-05-24T00:00:01+00:00",
                    "finished_at_epoch": 1,
                    "root": str(self.repo),
                    "run_dir": str(run_path),
                    "events_path": str(run_path / "events.jsonl"),
                    "trace_path": str(run_path / "trace.jsonl"),
                }
            ),
            encoding="utf-8",
        )
        (run_path / "events.jsonl").write_text("", encoding="utf-8")

        status = service.status(self.repo, run_id)
        context = service.context(self.repo, run_id)
        runs = service.runs(self.repo)

        self.assertEqual(status["status"], "FAILED")
        self.assertEqual(status["stage"], "plan")
        self.assertIn("exit code 9", status["error"])
        self.assertFalse(status["background_job"]["active"])
        self.assertEqual(status["background_job"]["status"], "failed")
        self.assertEqual(status["background_job"]["duration_ms"], 1000)
        self.assertEqual(status["background_job"]["exit_code"], 9)
        self.assertEqual(context["status"], "FAILED")
        self.assertEqual(context["background_job"]["status"], "failed")
        listed = next(item for item in runs["runs"] if item["run_id"] == run_id)
        self.assertEqual(listed["status"], "FAILED")
        self.assertEqual(listed["background_job"]["duration_ms"], 1000)

    def test_cancel_background_job_without_status_marks_canceled_and_releases_locks(self) -> None:
        from scripts.ai_flow import service

        run_id = "20260603-cancel-background"
        run_path = self.repo / ".ai" / "runs" / run_id
        run_path.mkdir(parents=True)
        service._acquire_lock(run_path, "plan", token="cancel-token")
        (run_path / "AGENT.lock").write_text("agent\ncancel-token\n", encoding="utf-8")
        service._record_job(
            run_path,
            {
                "background": True,
                "phase": "plan",
                "pid": 4321,
                "run_id": run_id,
                "task": "cancel background task",
                "started_at": "2026-06-03T00:00:00+00:00",
                "started_at_epoch": 0,
                "root": str(self.repo),
                "run_dir": str(run_path),
                "events_path": str(run_path / "events.jsonl"),
                "trace_path": str(run_path / "trace.jsonl"),
                "actions": service.background_followup_actions(run_id),
            },
        )

        with mock.patch.object(service, "_terminate_background_process", return_value={"attempted": True, "terminated": True}) as terminate:
            result = service.cancel_background_job(self.repo, run_id)

        terminate.assert_called_once_with(4321)
        self.assertTrue(result["ok"])
        self.assertTrue(result["canceled"])
        self.assertEqual(result["background_job"]["status"], "canceled")
        self.assertFalse(result["background_job"]["active"])
        self.assertFalse((run_path / "RUN.lock").exists())
        self.assertFalse((run_path / "AGENT.lock").exists())
        job = json.loads((run_path / "JOB.json").read_text(encoding="utf-8"))
        self.assertTrue(job["canceled"])
        self.assertIn("canceled_at", job)
        self.assertEqual(job["cancel_result"]["terminated"], True)
        status = service.status(self.repo, run_id)
        self.assertEqual(status["status"], "FAILED")
        self.assertEqual(status["background_job"]["status"], "canceled")
        self.assertIn("canceled", status["error"])
        events = service.events(self.repo, run_id)
        self.assertEqual(events["events"][-1]["action"], "cancel")

    def test_windows_background_termination_uses_pid_probe_for_exited_process(self) -> None:
        from scripts.ai_flow import service

        completed = subprocess.CompletedProcess(
            ["taskkill"],
            128,
            stdout="",
            stderr="localized operating system message",
        )
        with (
            mock.patch.object(service.os, "name", "nt"),
            mock.patch.object(service.subprocess, "run", return_value=completed) as taskkill,
            mock.patch.object(service, "_windows_process_is_active", return_value=False) as probe,
        ):
            result = service._terminate_background_process(4321)

        taskkill.assert_called_once_with(
            ["taskkill", "/PID", "4321", "/T", "/F"],
            capture_output=True,
            text=True,
            check=False,
        )
        probe.assert_called_once_with(4321)
        self.assertTrue(result["attempted"])
        self.assertFalse(result["terminated"])
        self.assertTrue(result["already_exited"])
        self.assertFalse(result["active_after_taskkill"])
        self.assertNotIn("error", result)

    def test_background_plan_cli_respects_explicit_run_id_collision(self) -> None:
        run_id = "20260524-background-explicit"
        first = run(
            ["python", str(self.script), "plan", "--task", "original background id", "--mock", "--run-id", run_id, "--json"],
            self.repo,
        )
        self.assertEqual(first.returncode, 0, first.stderr)

        second = run(
            [
                "python",
                str(self.script),
                "plan",
                "--task",
                "replacement background id",
                "--mock",
                "--background",
                "--run-id",
                run_id,
                "--json",
            ],
            self.repo,
        )

        self.assertNotEqual(second.returncode, 0)
        self.assertIn("already exists", second.stderr.lower())

    def test_background_plan_reserves_and_preserves_fast_child_artifacts(self) -> None:
        from scripts.ai_flow import service

        run_id = "20260524-background-fast-child"
        task = "background fast child"
        observed: dict[str, object] = {}
        real_popen = subprocess.Popen

        class FakeProcess:
            pid = 4321

            def poll(self):
                return None

        def fake_popen(command, *args, **kwargs):
            env = kwargs.get("env") or {}
            if env.get("PATCHBAY_BACKGROUND_PHASE") != "plan":
                return real_popen(command, *args, **kwargs)
            run_path = self.repo / ".ai" / "runs" / run_id
            observed["lock_at_spawn"] = (run_path / "RUN.lock").exists()
            observed["job_at_spawn"] = (run_path / "JOB.json").exists()
            observed["events_at_spawn"] = (run_path / "events.jsonl").exists()
            observed["reserved_run"] = env.get("PATCHBAY_RESERVED_RUN_ID")
            observed["inherited_lock"] = env.get("PATCHBAY_INHERITED_LOCK")
            observed["lock_token"] = env.get("PATCHBAY_LOCK_TOKEN")
            observed["wrapper_command"] = "-c" in command
            with mock.patch.dict(os.environ, env, clear=False):
                service.plan(self.repo, task=task, mock=True, run_id=run_id)
            return FakeProcess()

        with mock.patch.object(service.subprocess, "Popen", side_effect=fake_popen):
            result = service.start_background_phase(
                self.repo,
                "plan",
                task=task,
                run_id=run_id,
                mock=True,
            )

        run_path = self.repo / ".ai" / "runs" / run_id
        self.assertTrue(observed["lock_at_spawn"])
        self.assertTrue(observed["job_at_spawn"])
        self.assertTrue(observed["events_at_spawn"])
        self.assertEqual(observed["reserved_run"], run_id)
        self.assertEqual(observed["inherited_lock"], "plan")
        self.assertTrue(observed["lock_token"])
        self.assertTrue(observed["wrapper_command"])
        self.assertEqual(result["pid"], 4321)
        self.assertTrue((run_path / "JOB.json").exists())
        self.assertTrue((run_path / "STATUS.json").exists())
        self.assertFalse((run_path / "RUN.lock").exists())
        events = [
            json.loads(line)
            for line in (run_path / "events.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.assertIn(("plan", "start"), [(event["phase"], event["action"]) for event in events])
        self.assertIn(("plan", "success"), [(event["phase"], event["action"]) for event in events])

    def test_background_plan_cli_preserves_job_status_and_events(self) -> None:
        from scripts.ai_flow import service

        completed = run(
            ["python", str(self.script), "plan", "--task", "background durable", "--mock", "--background", "--json"],
            self.repo,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        run_path = Path(result["run_dir"])

        self.wait_for(lambda: (run_path / "STATUS.json").exists() and (run_path / "JOB.json").exists())
        def completed_events() -> list[dict]:
            if not (run_path / "events.jsonl").exists():
                return []
            entries = [
                json.loads(line)
                for line in (run_path / "events.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            actions = [(event["phase"], event["action"]) for event in entries]
            return entries if ("plan", "success") in actions else []

        events = self.wait_for(completed_events)

        status = json.loads((run_path / "STATUS.json").read_text(encoding="utf-8"))
        def completed_job() -> dict | None:
            payload = json.loads((run_path / "JOB.json").read_text(encoding="utf-8"))
            return payload if "exit_code" in payload else None

        job = self.wait_for(completed_job)
        status_payload = service.status(self.repo, result["run_id"])
        actions = [(event["phase"], event["action"]) for event in events]
        self.assertEqual(status["run_id"], result["run_id"])
        self.assertEqual(job["pid"], result["pid"])
        self.assertEqual(job["exit_code"], 0)
        self.assertEqual(status_payload["background_job"]["status"], "finished")
        self.assertFalse(status_payload["background_job"]["active"])
        self.assertIsInstance(status_payload["background_job"]["duration_ms"], int)
        self.assertIn(("plan", "start"), actions)
        self.assertIn(("plan", "success"), actions)
        self.assertFalse((run_path / "RUN.lock").exists())

    def test_background_plan_releases_lock_when_child_exits_before_handoff(self) -> None:
        from scripts.ai_flow import service

        run_id = "20260524-child-exits-before-handoff"
        real_popen = subprocess.Popen

        class DeadProcess:
            pid = 5432
            returncode = 2

            def poll(self):
                return self.returncode

        def fake_popen(command, *args, **kwargs):
            env = kwargs.get("env") or {}
            if env.get("PATCHBAY_BACKGROUND_PHASE") != "plan":
                return real_popen(command, *args, **kwargs)
            return DeadProcess()

        with mock.patch.object(service.subprocess, "Popen", side_effect=fake_popen):
            result = service.start_background_phase(
                self.repo,
                "plan",
                task="child exits early",
                run_id=run_id,
                mock=True,
            )

        run_path = self.repo / ".ai" / "runs" / run_id
        self.assertEqual(result["pid"], 5432)
        self.assertEqual(result["exit_code"], 2)
        self.assertIn("finished_at", result)
        self.assertFalse((run_path / "RUN.lock").exists())

    def test_background_process_reaper_records_exit_and_releases_lock(self) -> None:
        from scripts.ai_flow import service

        run_id = "20260524-background-reaper"
        run_path = self.repo / ".ai" / "runs" / run_id
        run_path.mkdir(parents=True)
        service._acquire_lock(run_path, "plan", token="reaper-token")
        service._record_job(
            run_path,
            {
                "background": True,
                "phase": "plan",
                "pid": 8765,
                "run_id": run_id,
                "started_at": "2026-05-24T00:00:00+00:00",
                "started_at_epoch": 0,
            },
        )

        class FakeProcess:
            pid = 8765

            def wait(self):
                return 7

        service._track_background_process(
            FakeProcess(),
            run_path,
            on_exit=lambda _exit_code: service._release_lock(run_path, token="reaper-token"),
        )

        job = self.wait_for(
            lambda: (
                json.loads((run_path / "JOB.json").read_text(encoding="utf-8"))
                if "finished_at" in (run_path / "JOB.json").read_text(encoding="utf-8")
                else None
            )
        )
        self.assertEqual(job["exit_code"], 7)
        self.assertIn("finished_at", job)
        self.assertFalse((run_path / "RUN.lock").exists())

    def test_events_follow_json_returns_json_payload(self) -> None:
        planned = self.cli_json("plan", "--task", "follow json", "--mock")
        completed = run(
            ["python", str(self.script), "events", planned["run_id"], "--follow", "--json"],
            self.repo,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(result["run_id"], planned["run_id"])
        self.assertEqual(result["since"], 0)
        self.assertGreaterEqual(result["returned"], 2)
        actions = [event["action"] for event in result["events"]]
        self.assertIn("start", actions)
        self.assertIn("success", actions)

    def test_events_follow_plain_streams_only_json_lines(self) -> None:
        planned = self.cli_json("plan", "--task", "follow plain", "--mock")
        completed = run(
            ["python", str(self.script), "events", planned["run_id"], "--follow"],
            self.repo,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        lines = [line for line in completed.stdout.splitlines() if line.strip()]
        self.assertGreaterEqual(len(lines), 2)
        parsed = [json.loads(line) for line in lines]
        self.assertTrue(all("action" in event for event in parsed))
        self.assertNotIn("run_id:", completed.stdout)

    def test_events_follow_phase_advances_by_raw_event_index(self) -> None:
        planned = self.cli_json("plan", "--task", "follow phase", "--mock")
        run_path = self.repo / ".ai" / "runs" / planned["run_id"]
        path = run_path / "events.jsonl"
        plan_start, plan_success = path.read_text(encoding="utf-8").splitlines()
        noise = {
            "timestamp": "2026-05-24T00:00:00+00:00",
            "phase": "write",
            "action": "start",
            "status": "RUNNING",
        }
        path.write_text(
            "\n".join([plan_start, json.dumps(noise, sort_keys=True), plan_success]) + "\n",
            encoding="utf-8",
            newline="\n",
        )

        completed = run(
            ["python", str(self.script), "events", planned["run_id"], "--follow", "--phase", "plan", "--json"],
            self.repo,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual([event["action"] for event in result["events"]], ["start", "success"])

    def test_plan_rejects_existing_run_id_without_overwriting(self) -> None:
        run_id = "20260524-existing-run"
        first = run(
            ["python", str(self.script), "plan", "--task", "original task", "--mock", "--run-id", run_id, "--json"],
            self.repo,
        )
        self.assertEqual(first.returncode, 0, first.stderr)
        run_path = self.repo / ".ai" / "runs" / run_id
        original_task = (run_path / "TASK.md").read_text(encoding="utf-8")

        second = run(
            ["python", str(self.script), "plan", "--task", "replacement task", "--mock", "--run-id", run_id, "--json"],
            self.repo,
        )

        self.assertNotEqual(second.returncode, 0)
        self.assertIn("already exists", second.stderr.lower())
        self.assertEqual((run_path / "TASK.md").read_text(encoding="utf-8"), original_task)
        self.assertNotIn("replacement task", original_task)

    def test_plan_auto_run_id_collision_gets_unique_suffix(self) -> None:
        from scripts.ai_flow import service

        with mock.patch.object(service, "new_run_id", return_value="20260524-auto-collision"):
            first = service.plan(self.repo, task="first auto", mock=True)
            second = service.plan(self.repo, task="second auto", mock=True)

        self.assertEqual(first["run_id"], "20260524-auto-collision")
        self.assertEqual(second["run_id"], "20260524-auto-collision-2")
        self.assertTrue((self.repo / ".ai" / "runs" / first["run_id"] / "TASK.md").exists())
        self.assertTrue((self.repo / ".ai" / "runs" / second["run_id"] / "TASK.md").exists())

    def test_plan_auto_run_id_retries_when_directory_appears_during_reservation(self) -> None:
        from scripts.ai_flow import service

        real_mkdir = Path.mkdir
        raced = {"done": False}

        def racing_mkdir(path_self, *args, **kwargs):
            if path_self == self.repo / ".ai" / "runs" / "20260524-racy-auto" and not raced["done"]:
                raced["done"] = True
                real_mkdir(path_self, parents=True, exist_ok=True)
                raise FileExistsError("simulated concurrent reservation")
            return real_mkdir(path_self, *args, **kwargs)

        with mock.patch.object(service, "new_run_id", return_value="20260524-racy-auto"):
            with mock.patch.object(Path, "mkdir", new=racing_mkdir):
                result = service.plan(self.repo, task="racy auto", mock=True)

        self.assertEqual(result["run_id"], "20260524-racy-auto-2")
        self.assertTrue((self.repo / ".ai" / "runs" / "20260524-racy-auto").exists())
        self.assertTrue((self.repo / ".ai" / "runs" / "20260524-racy-auto-2" / "STATUS.json").exists())

    def test_run_lock_uses_atomic_create(self) -> None:
        from scripts.ai_flow import service

        flags_seen: list[int] = []
        real_open = os.open
        run_path = self.repo / ".ai" / "runs" / "lock-atomic"
        run_path.mkdir(parents=True)

        def spy_open(path, flags, *args, **kwargs):
            flags_seen.append(flags)
            return real_open(path, flags, *args, **kwargs)

        with mock.patch.object(service.os, "open", side_effect=spy_open):
            service._acquire_lock(run_path, "write")

        self.assertTrue(flags_seen)
        self.assertTrue(flags_seen[0] & os.O_CREAT)
        self.assertTrue(flags_seen[0] & os.O_EXCL)
        service._release_lock(run_path)

    def test_status_exposes_current_phase_and_effective_providers(self) -> None:
        planned = self.cli_json("plan", "--task", "status detail", "--mock")

        status = self.cli_json("status", planned["run_id"])

        self.assertEqual(status["current_phase"], "plan")
        self.assertIn("effective_phase_providers", status)
        self.assertEqual(status["effective_phase_providers"]["plan"]["provider"], "claude_cli")
        self.assertEqual(status["effective_phase_providers"]["write"]["provider"], "reasonix_cli")
        self.assertIn("next_commands", status)
        self.assertIn("run_metrics", status)
        self.assertEqual(status["run_metrics"]["event_count"], status["event_count"])
