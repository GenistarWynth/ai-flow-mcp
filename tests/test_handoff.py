from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.ai_flow import mcp_server, service
from scripts.ai_flow.events import append_event
from scripts.ai_flow.handoff import build_handoff_context
from scripts.ai_flow.state import mark_failed
from scripts.ai_flow.trace import append_trace


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


class HandoffContextTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = Path(tempfile.mkdtemp(prefix="patchbay-handoff-"))
        self.repo = self.tempdir / "repo"
        self.repo.mkdir()
        self.script = PROJECT_ROOT / "scripts" / "patchbay"
        run(["git", "init"], self.repo)
        run(["git", "config", "user.email", "patchbay@example.test"], self.repo)
        run(["git", "config", "user.name", "Patchbay tests"], self.repo)
        (self.repo / "README.md").write_text("# Handoff Repo\n", encoding="utf-8")
        (self.repo / ".ai").mkdir(parents=True, exist_ok=True)
        (self.repo / ".ai" / "patchbay.toml").write_text(
            "[workflow]\nallow_apply_without_tests = true\n",
            encoding="utf-8",
        )
        (self.repo / ".gitignore").write_text(
            ".ai/runs/\n.ai/logs/\n.ai/worktrees/\n.ai/patchbay.toml\n.patchbay-worktrees/\n",
            encoding="utf-8",
        )
        run(["git", "add", "README.md", ".gitignore"], self.repo)
        run(["git", "commit", "-m", "initial"], self.repo)

    def tearDown(self) -> None:
        shutil.rmtree(self.tempdir, ignore_errors=True)

    def cli_json(self, *args: str) -> dict:
        completed = run(["python", str(self.script), *args, "--json"], self.repo)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return json.loads(completed.stdout)

    def test_context_summarizes_planned_run_and_next_human_gate(self) -> None:
        planned = self.cli_json("plan", "--task", "handoff context", "--mock")

        context = service.context(self.repo, planned["run_id"])

        self.assertEqual(context["run_id"], planned["run_id"])
        self.assertEqual(context["status"], "PLANNED")
        self.assertEqual(context["current_phase"], "plan")
        self.assertIn("PLANNED", context["handoff_summary"])
        self.assertEqual(context["next_actions"][0]["name"], "approve")
        self.assertEqual(context["next_actions"][0]["tool"], "patchbay_approve")
        self.assertTrue(context["next_actions"][0]["safe"])
        self.assertTrue(context["next_actions"][0]["requires_human_confirmation"])
        metrics = context["run_metrics"]
        self.assertTrue(metrics["duration_known"])
        self.assertEqual(metrics["duration_source"], "event_or_timestamp")
        self.assertIn("plan", metrics["phase_durations_ms"])
        self.assertEqual(metrics["phase_attempts"]["plan"], 1)
        self.assertEqual(metrics["event_count"], 2)
        self.assertEqual(metrics["trace_count"], 0)
        self.assertFalse(metrics["cost"]["known"])
        activity = context["agent_activity"]
        self.assertIn("Patchbay Agent", activity["headline"])
        self.assertEqual(activity["tone"], "ready")
        self.assertEqual(activity["current_step"]["label"], "规划")
        self.assertEqual(activity["next_action"]["name"], "approve")
        self.assertEqual(activity["next_action"]["tool"], "patchbay_approve")
        self.assertEqual(activity["conversation_state"]["task"], "handoff context")
        self.assertEqual(activity["conversation_state"]["phase_label"], "规划")
        self.assertEqual(activity["conversation_state"]["suggestions"][0]["action"], "approve")
        self.assertTrue(activity["conversation_state"]["suggestions"][0]["requires_human_confirmation"])
        self.assertIn("确认", activity["conversation_state"]["composer_placeholder"])
        self.assertEqual([card["key"] for card in activity["gate_cards"]], ["approval", "tests", "review", "apply"])
        self.assertEqual(activity["health_cards"][0]["key"], "economy_route")
        self.assertEqual(activity["health_cards"][0]["status"], "command_not_ready")
        self.assertEqual(activity["health_cards"][0]["tone"], "blocked")
        self.assertEqual(activity["health_cards"][0]["coverage_percent"], 0)
        self.assertEqual(activity["health_cards"][0]["action"]["id"], "configure_reasonix_command")
        self.assertEqual(activity["health_cards"][0]["action"]["kind"], "local_agent")
        self.assertEqual(activity["health_cards"][0]["action"]["message"], "configure reasonix command")
        self.assertIn("commands.reasonix", activity["health_cards"][0]["action"]["command"])
        self.assertNotIn("provider", activity["headline"].lower())
        self.assertEqual(activity["messages"][0]["kind"], "event")
        artifact = {item["name"]: item for item in context["artifacts"]}
        self.assertEqual(artifact["PLAN.md"]["purpose"], "approved plan")
        self.assertTrue(artifact["PLAN.md"]["path"].endswith("PLAN.md"))
        self.assertEqual(context["timeline"][0]["source"], "event")
        self.assertEqual(context["timeline"][0]["index"], 0)
        self.assertEqual(context["cursors"]["event"], 2)
        self.assertEqual(context["cursors"]["trace"], 0)

    def test_context_marks_write_blocked_when_reasonix_command_is_missing(self) -> None:
        planned = self.cli_json("plan", "--task", "blocked write handoff", "--mock")
        self.cli_json("approve", planned["run_id"])

        context = service.context(self.repo, planned["run_id"])

        self.assertEqual(context["status"], "APPROVED")
        self.assertEqual(context["next_actions"][0]["name"], "write")
        self.assertFalse(context["next_actions"][0]["safe"])
        self.assertEqual(context["next_actions"][0]["alternative_action"]["id"], "configure_reasonix_command")
        self.assertIn("commands.reasonix", context["next_actions"][0]["reason"])
        self.assertEqual(context["agent_activity"]["conversation_state"]["suggestions"][0]["safe"], False)
        self.assertEqual(
            context["agent_activity"]["conversation_state"]["suggestions"][0]["alternative_action"]["id"],
            "configure_reasonix_command",
        )

    def test_context_health_card_prefers_routing_evidence_actions(self) -> None:
        status_data = {
            "run_metrics": {
                "routing_evidence": {
                    "summary": "Economy route is configured; waiting for fix provider evidence.",
                    "coverage": {"observed_economy_percent": 50},
                    "economy_health": {
                        "status": "pending_evidence",
                        "severity": "info",
                        "summary": "Economy route is configured; waiting for fix provider evidence.",
                        "recommendation": "Watch provider events.",
                        "next_action": "wait_for_routing_evidence",
                    },
                    "actions": [
                        {
                            "id": "custom_structured_action",
                            "label": "Open routing evidence",
                            "kind": "diagnostic_tab",
                            "tab": "Trace",
                            "safe": True,
                            "reason": "Use the service-provided routing action.",
                        }
                    ],
                }
            }
        }

        run_path = self.repo / ".ai" / "runs" / "structured-action-run"
        run_path.mkdir(parents=True)

        activity = build_handoff_context(run_path=run_path, status_data=status_data)["agent_activity"]

        card = activity["health_cards"][0]
        self.assertEqual(card["action"]["id"], "custom_structured_action")
        self.assertEqual(card["action"]["reason"], "Use the service-provided routing action.")

    def test_context_marks_apply_as_human_confirmed_technical_gate(self) -> None:
        planned = self.cli_json("plan", "--task", "ready for apply", "--mock")
        run_id = planned["run_id"]
        self.cli_json("approve", run_id)
        self.cli_json("write", run_id, "--mock")
        self.cli_json("test", run_id)
        self.cli_json("review", run_id, "--mock")

        context = self.cli_json("context", run_id)

        self.assertTrue(context["gate_state"]["ready_to_apply"])
        self.assertEqual(context["next_actions"][0]["name"], "apply")
        self.assertEqual(context["next_actions"][0]["tool"], "patchbay_apply")
        self.assertTrue(context["next_actions"][0]["safe"])
        self.assertTrue(context["next_actions"][0]["requires_human_confirmation"])
        activity = context["agent_activity"]
        self.assertEqual(activity["next_action"]["name"], "apply")
        self.assertTrue(activity["next_action"]["requires_human_confirmation"])
        apply_gate = next(card for card in activity["gate_cards"] if card["key"] == "apply")
        self.assertEqual(apply_gate["status"], "ready")
        self.assertEqual(apply_gate["tone"], "ready")
        self.assertIn("review", [item["phase"] for item in context["provider_trail"]])

    def test_context_exposes_failed_recovery_guidance_without_next_action(self) -> None:
        planned = self.cli_json("plan", "--task", "failed handoff", "--mock")
        run_id = planned["run_id"]
        run_dir = self.repo / ".ai" / "runs" / run_id
        guidance = "Ask the planner to emit valid JSON inside the sentinel block."
        mark_failed(
            run_dir,
            error="Planner JSON could not be parsed: Expecting value",
            stage="plan",
            suggested_next_action=guidance,
        )

        context = service.context(self.repo, run_id)

        self.assertEqual(context["status"], "FAILED")
        self.assertEqual(context["current_phase"], "plan")
        self.assertEqual(context["next_actions"], [])
        self.assertEqual(context["failure_recovery"]["stage"], "plan")
        self.assertEqual(context["failure_recovery"]["suggested_next_action"], guidance)
        self.assertIn("PLAN.md", context["failure_recovery"]["artifacts"])
        activity = context["agent_activity"]
        self.assertEqual(activity["tone"], "failed")
        self.assertIsNone(activity["next_action"])
        self.assertIn(guidance, activity["conversation_state"]["next_step"])
        self.assertEqual(activity["conversation_state"]["suggestions"], [])
        self.assertIn("修复", activity["conversation_state"]["composer_placeholder"])

    def test_context_can_merge_trace_when_requested_and_returns_cursors(self) -> None:
        planned = self.cli_json("plan", "--task", "trace context", "--mock")
        run_dir = self.repo / ".ai" / "runs" / planned["run_id"]
        append_trace(run_dir, phase="write", agent="reasonix_cli", action="stdout", status="ok", detail="chunk")

        context = service.context(self.repo, planned["run_id"], since_event=1, include_trace=True)

        self.assertEqual(context["cursors"], {"event": 2, "trace": 1})
        self.assertEqual([item["source"] for item in context["timeline"]], ["event", "trace"])
        self.assertEqual(context["timeline"][0]["index"], 1)
        self.assertEqual(context["timeline"][1]["source"], "trace")
        self.assertEqual(context["timeline"][1]["agent"], "reasonix_cli")
        messages = context["agent_activity"]["messages"]
        self.assertEqual(messages[1]["kind"], "agent")
        self.assertEqual(messages[1]["provider"], "reasonix_cli")

    def test_context_cursors_track_next_raw_line_index(self) -> None:
        planned = self.cli_json("plan", "--task", "raw cursor context", "--mock")
        run_dir = self.repo / ".ai" / "runs" / planned["run_id"]
        events_path = run_dir / "events.jsonl"
        events_path.write_text(events_path.read_text(encoding="utf-8") + "\n{bad json\n", encoding="utf-8")
        append_trace(run_dir, phase="write", action="stdout", status="ok", detail="first")
        (run_dir / "trace.jsonl").write_text(
            (run_dir / "trace.jsonl").read_text(encoding="utf-8") + "\n{bad json\n",
            encoding="utf-8",
        )

        context = service.context(self.repo, planned["run_id"], since_event=2, since_trace=1, include_trace=True)

        self.assertEqual(context["cursors"]["event"], 4)
        self.assertEqual(context["cursors"]["trace"], 3)
        self.assertEqual([item["source"] for item in context["timeline"]], [])
        self.assertEqual(context["agent_activity"]["messages"], [])
        self.assertIn("conversation_state", context["agent_activity"])

    def test_mcp_context_and_legacy_alias_wrap_same_payload(self) -> None:
        planned = self.cli_json("plan", "--task", "mcp context", "--mock")
        original_root = mcp_server.ROOT
        try:
            mcp_server.ROOT = self.repo
            canonical = mcp_server.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": "patchbay_context", "arguments": {"run_id": planned["run_id"]}},
                }
            )
            legacy = mcp_server.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {"name": "ai_flow_context", "arguments": {"run_id": planned["run_id"]}},
                }
            )
        finally:
            mcp_server.ROOT = original_root

        canonical_payload = json.loads(canonical["result"]["content"][0]["text"])
        legacy_payload = json.loads(legacy["result"]["content"][0]["text"])
        self.assertEqual(canonical_payload["run_id"], planned["run_id"])
        self.assertEqual(legacy_payload["run_id"], planned["run_id"])
        self.assertEqual(canonical_payload["next_actions"], legacy_payload["next_actions"])
        self.assertEqual(
            canonical_payload["agent_activity"]["health_cards"][0]["action"],
            legacy_payload["agent_activity"]["health_cards"][0]["action"],
        )
        self.assertEqual(
            canonical_payload["agent_activity"]["health_cards"][0]["action"]["id"],
            "configure_reasonix_command",
        )

    def test_metrics_command_and_mcp_tool_expose_efficiency_digest(self) -> None:
        planned = self.cli_json("plan", "--task", "metrics digest", "--mock")
        run_id = planned["run_id"]
        run_dir = self.repo / ".ai" / "runs" / run_id
        append_event(
            run_dir,
            phase="plan",
            provider="mock",
            model="mock-model",
            action="usage",
            status="OK",
            run_id=run_id,
            token_usage={"input_tokens": 800, "output_tokens": 200, "cached_tokens": 100, "total_tokens": 1100},
            cost={"currency": "USD", "estimated_total": 0.05},
        )

        cli_metrics = self.cli_json("metrics", run_id)

        self.assertEqual(cli_metrics["run_id"], run_id)
        self.assertEqual(cli_metrics["status"], "PLANNED")
        self.assertIn("plan", cli_metrics["run_metrics"]["phase_durations_ms"])
        self.assertEqual(cli_metrics["run_metrics"]["token_usage"]["total_tokens"], 1100)
        self.assertEqual(cli_metrics["run_metrics"]["token_usage"]["by_phase"]["plan"]["cached_tokens"], 100)
        self.assertEqual(cli_metrics["run_metrics"]["cost"]["estimated_total"], 0.05)
        self.assertEqual(cli_metrics["run_metrics"]["cost"]["by_phase"]["plan"]["currency"], "USD")
        provider_usage = next(
            item
            for item in cli_metrics["run_metrics"]["provider_usage"]
            if item["phase"] == "plan" and item["provider"] == "mock" and item["model"] == "mock-model"
        )
        self.assertEqual(provider_usage["token_usage"]["total_tokens"], 1100)
        self.assertEqual(provider_usage["token_usage"]["cached_tokens"], 100)
        self.assertEqual(provider_usage["total_tokens"], 1100)
        self.assertEqual(provider_usage["cost"]["estimated_total"], 0.05)
        self.assertEqual(provider_usage["cost"]["currency"], "USD")
        original_root = mcp_server.ROOT
        try:
            mcp_server.ROOT = self.repo
            response = mcp_server.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": "patchbay_metrics", "arguments": {"run_id": run_id}},
                }
            )
        finally:
            mcp_server.ROOT = original_root

        payload = json.loads(response["result"]["content"][0]["text"])
        self.assertEqual(payload["run_metrics"]["event_count"], cli_metrics["run_metrics"]["event_count"])

    def test_metrics_groups_usage_by_phase_tier(self) -> None:
        planned = self.cli_json("plan", "--task", "tier usage digest", "--mock")
        run_id = planned["run_id"]
        run_dir = self.repo / ".ai" / "runs" / run_id
        append_event(
            run_dir,
            phase="write",
            provider="reasonix_cli",
            model="deepseek-v4-pro",
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

        cli_metrics = self.cli_json("metrics", run_id)

        tiers = cli_metrics["run_metrics"]["tier_usage"]
        self.assertEqual(tiers["economy"]["phases"], ["write", "fix"])
        self.assertEqual(tiers["economy"]["duration_ms"], 3000)
        self.assertEqual(tiers["economy"]["token_usage"]["total_tokens"], 1000)
        self.assertEqual(tiers["economy"]["token_usage"]["token_percent"], 50.0)
        self.assertEqual(tiers["economy"]["cost"]["estimated_total"], 0.05)
        self.assertEqual(tiers["economy"]["cost"]["cost_percent"], 20.0)
        self.assertEqual(tiers["supervision"]["token_usage"]["total_tokens"], 1000)
        self.assertEqual(tiers["supervision"]["cost"]["estimated_total"], 0.2)

    def test_metrics_exposes_not_configured_economy_health(self) -> None:
        (self.repo / ".ai" / "patchbay.toml").write_text(
            "[workflow]\nallow_apply_without_tests = true\n\n"
            "[phases.write]\nprovider = \"mock\"\nmodel = \"mock-model\"\n\n"
            "[phases.fix]\nprovider = \"mock\"\nmodel = \"mock-model\"\n",
            encoding="utf-8",
        )
        planned = self.cli_json("plan", "--task", "custom route health", "--mock")

        cli_metrics = self.cli_json("metrics", planned["run_id"])

        health = cli_metrics["routing_evidence"]["economy_health"]
        self.assertEqual(health["status"], "not_configured")
        self.assertEqual(health["severity"], "warning")
        self.assertEqual(health["missing_config_phases"], ["write", "fix"])
        self.assertEqual(health["next_action"], "apply_economy_profile")
        self.assertEqual(cli_metrics["routing_evidence"]["actions"][0]["id"], "apply_economy_profile")
        self.assertEqual(cli_metrics["actions"][0]["message"], "apply economy profile")
        context = self.cli_json("context", planned["run_id"])
        card = context["agent_activity"]["health_cards"][0]
        self.assertEqual(card["status"], "not_configured")
        self.assertEqual(card["action"]["id"], "apply_economy_profile")
        self.assertEqual(card["action"]["kind"], "local_agent")
        self.assertEqual(card["action"]["message"], "apply economy profile")

    def test_fix_loop_context_tracks_provider_trail_and_next_action(self) -> None:
        planned = self.cli_json("plan", "--task", "fix handoff", "--mock")
        run_id = planned["run_id"]
        self.cli_json("approve", run_id)
        self.cli_json("write", run_id, "--mock")
        self.cli_json("test", run_id)
        verdicts = [
            "CHANGES_REQUESTED\n\nBlocking Issues:\n1. needs repair\n\nRequired Fixes:\n1. add repair\n",
            "PASS\n\nSummary:\nrepair accepted\n",
        ]

        with mock.patch.dict(service.REVIEWERS, {"mock": mock.Mock(side_effect=verdicts)}):
            service.review(self.repo, run_id, mock=True)
            first_context = service.context(self.repo, run_id)
            self.assertEqual(first_context["next_actions"][0]["name"], "fix")
            service.fix(self.repo, run_id, mock=True)
            service.test(self.repo, run_id)
            service.review(self.repo, run_id, mock=True)

        context = service.context(self.repo, run_id)

        phases = [item["phase"] for item in context["provider_trail"]]
        self.assertGreaterEqual(phases.count("review"), 2)
        self.assertIn("fix", phases)
        metrics = context["run_metrics"]
        self.assertGreaterEqual(metrics["phase_attempts"]["review"], 2)
        self.assertEqual(metrics["phase_attempts"]["fix"], 1)
        self.assertIn("fix", metrics["phase_durations_ms"])
        self.assertTrue(any(item["phase"] == "review" for item in metrics["provider_usage"]))
        self.assertEqual(context["status"], "REVIEWED_PASS")
        self.assertEqual(context["next_actions"][0]["name"], "apply")


if __name__ == "__main__":
    unittest.main()
