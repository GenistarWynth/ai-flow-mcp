"""Tests for event emission, ordering, and cross-host visibility."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.ai_flow.events import append_event, event_count, latest_event, list_events


class EventsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_append_and_list(self) -> None:
        append_event(self.tmp, phase="plan", provider="claude_cli", model="claude-opus-4-7",
                     action="start", status="RUNNING", run_id="r1")
        append_event(self.tmp, phase="plan", provider="claude_cli", model="claude-opus-4-7",
                     action="success", status="PLANNED", detail="Plan done", run_id="r1")

        events = list_events(self.tmp)
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["phase"], "plan")
        self.assertEqual(events[0]["action"], "start")
        self.assertEqual(events[1]["action"], "success")

    def test_since_filter(self) -> None:
        for i in range(5):
            append_event(self.tmp, phase="write", action="step", status="OK", run_id="r1")
        events = list_events(self.tmp, since=2)
        self.assertEqual(len(events), 3)

    def test_phase_filter(self) -> None:
        append_event(self.tmp, phase="plan", action="start", status="RUNNING", run_id="r1")
        append_event(self.tmp, phase="write", action="start", status="RUNNING", run_id="r1")
        append_event(self.tmp, phase="plan", action="success", status="DONE", run_id="r1")

        plan_events = list_events(self.tmp, phase="plan")
        self.assertEqual(len(plan_events), 2)
        self.assertTrue(all(e["phase"] == "plan" for e in plan_events))

    def test_latest_event(self) -> None:
        self.assertIsNone(latest_event(self.tmp))
        append_event(self.tmp, phase="review", action="start", status="RUNNING", run_id="r1")
        append_event(self.tmp, phase="review", action="success", status="PASS", run_id="r1")
        latest = latest_event(self.tmp)
        self.assertIsNotNone(latest)
        assert latest is not None
        self.assertEqual(latest["status"], "PASS")

    def test_event_count(self) -> None:
        self.assertEqual(event_count(self.tmp), 0)
        append_event(self.tmp, phase="test", action="start", status="RUNNING", run_id="r1")
        self.assertEqual(event_count(self.tmp), 1)

    def test_event_fields(self) -> None:
        append_event(
            self.tmp,
            phase="apply",
            provider="reasonix_cli",
            model="",
            command_key="reasonix",
            action="apply_granted",
            status="APPLIED",
            detail="Applied FINAL.diff to /repo",
            run_id="abc-123",
            artifact_paths=["FINAL.diff"],
            duration_ms=1234,
            next_action="cleanup",
            token_usage={"input_tokens": 100, "output_tokens": 25, "total_tokens": 125},
            cost={"currency": "USD", "estimated_total": 0.0125},
        )
        events = list_events(self.tmp)
        self.assertEqual(len(events), 1)
        e = events[0]
        self.assertIn("timestamp", e)
        self.assertEqual(e["phase"], "apply")
        self.assertEqual(e["action"], "apply_granted")
        self.assertEqual(e["status"], "APPLIED")
        self.assertEqual(e["run_id"], "abc-123")
        self.assertEqual(e["detail"], "Applied FINAL.diff to /repo")
        self.assertEqual(e["artifact_paths"], ["FINAL.diff"])
        self.assertEqual(e["duration_ms"], 1234)
        self.assertEqual(e["next_action"], "cleanup")
        self.assertEqual(e["token_usage"]["total_tokens"], 125)
        self.assertEqual(e["cost"]["estimated_total"], 0.0125)
        self.assertEqual(e["provider"], "reasonix_cli")
        self.assertEqual(e["command_key"], "reasonix")
        # model omitted when empty
        self.assertNotIn("model", e)

    def test_events_file_is_jsonl(self) -> None:
        append_event(self.tmp, phase="fix", action="retry", status="RETRY", run_id="r1")
        path = self.tmp / "events.jsonl"
        self.assertTrue(path.exists())
        lines = path.read_text().strip().splitlines()
        self.assertEqual(len(lines), 1)
        parsed = json.loads(lines[0])
        self.assertEqual(parsed["phase"], "fix")

    def test_background_follow_schema_is_available(self) -> None:
        from scripts.ai_flow.mcp_server import handle

        response = handle({"method": "tools/list", "id": 1, "params": {}})
        assert response is not None
        tools = {tool["name"]: tool for tool in response["result"]["tools"]}
        self.assertIn("background", tools["patchbay_plan"]["inputSchema"]["properties"])
        self.assertIn("since", tools["patchbay_events"]["inputSchema"]["properties"])


if __name__ == "__main__":
    unittest.main()
