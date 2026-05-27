from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.ai_flow import mcp_server, service
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
        activity = context["agent_activity"]
        self.assertIn("Patchbay Agent", activity["headline"])
        self.assertEqual(activity["tone"], "ready")
        self.assertEqual(activity["current_step"]["label"], "规划")
        self.assertEqual(activity["next_action"]["name"], "approve")
        self.assertEqual(activity["next_action"]["tool"], "patchbay_approve")
        self.assertEqual([card["key"] for card in activity["gate_cards"]], ["approval", "tests", "review", "apply"])
        self.assertNotIn("provider", activity["headline"].lower())
        self.assertEqual(activity["messages"][0]["kind"], "event")
        artifact = {item["name"]: item for item in context["artifacts"]}
        self.assertEqual(artifact["PLAN.md"]["purpose"], "approved plan")
        self.assertTrue(artifact["PLAN.md"]["path"].endswith("PLAN.md"))
        self.assertEqual(context["timeline"][0]["source"], "event")
        self.assertEqual(context["timeline"][0]["index"], 0)
        self.assertEqual(context["cursors"]["event"], 2)
        self.assertEqual(context["cursors"]["trace"], 0)

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
        self.assertEqual(context["status"], "REVIEWED_PASS")
        self.assertEqual(context["next_actions"][0]["name"], "apply")


if __name__ == "__main__":
    unittest.main()
