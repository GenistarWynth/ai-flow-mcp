from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.ai_flow import service
from scripts.ai_flow.adapters.reasonix_writer import _TraceRecorder
from scripts.ai_flow.state import create_status


class TraceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_append_and_list_trace_supports_since_phase_and_malformed_lines(self) -> None:
        from scripts.ai_flow.trace import append_trace, list_trace, trace_count

        append_trace(self.tmp, phase="write", action="stdout", status="ok", detail="first")
        append_trace(self.tmp, phase="plan", action="stdout", status="ok", detail="hidden")
        (self.tmp / "trace.jsonl").write_text(
            (self.tmp / "trace.jsonl").read_text(encoding="utf-8") + "{bad json\n",
            encoding="utf-8",
        )
        append_trace(self.tmp, phase="write", action="stderr", status="warn", detail="second")

        entries = list_trace(self.tmp, since=1, phase="write")

        self.assertEqual([entry["action"] for entry in entries], ["stderr"])
        self.assertEqual(entries[0]["index"], 3)
        self.assertEqual(trace_count(self.tmp), 4)

    def test_empty_or_missing_trace_file_returns_empty_list(self) -> None:
        from scripts.ai_flow.trace import list_trace, trace_count

        self.assertEqual(list_trace(self.tmp), [])
        self.assertEqual(trace_count(self.tmp), 0)
        (self.tmp / "trace.jsonl").write_text("", encoding="utf-8")
        self.assertEqual(list_trace(self.tmp), [])
        self.assertEqual(trace_count(self.tmp), 0)

    def test_list_trace_streams_without_reading_whole_file(self) -> None:
        from scripts.ai_flow.trace import list_trace, trace_count

        (self.tmp / "trace.jsonl").write_text(
            '{"phase":"write","action":"stdout"}\n{"phase":"write","action":"stderr"}\n',
            encoding="utf-8",
        )

        with patch.object(Path, "read_text", side_effect=AssertionError("read_text should not be used")):
            self.assertEqual(trace_count(self.tmp), 2)
            self.assertEqual([entry["action"] for entry in list_trace(self.tmp, since=1)], ["stderr"])

    def test_append_trace_redacts_raw_payload_and_summarizes_default_fields(self) -> None:
        from scripts.ai_flow.trace import append_trace, list_trace

        append_trace(
            self.tmp,
            phase="write",
            agent="reasonix",
            action="session/request_permission",
            tool="edit",
            path="src/app.py",
            status="requested",
            detail="permission requested",
            raw={
                "token": "sk-test-secret-value",
                "authorization": "Bearer very-secret-auth",
                "cookie": "sessionid=very-secret-cookie",
                "prompt": "copy the whole repository",
                "diff": "x" * 900,
                "safe": "shown",
            },
            env={"API_TOKEN": "sk-test-secret-value"},
        )

        entry = list_trace(self.tmp)[0]
        self.assertEqual(entry["agent"], "reasonix")
        self.assertEqual(entry["phase"], "write")
        self.assertEqual(entry["action"], "session/request_permission")
        self.assertEqual(entry["tool"], "edit")
        self.assertEqual(entry["path"], "src/app.py")
        self.assertEqual(entry["status"], "requested")
        self.assertEqual(entry["detail"], "permission requested")
        raw_text = json.dumps(entry["raw"], sort_keys=True)
        self.assertIn("***REDACTED***", raw_text)
        self.assertNotIn("sk-test-secret-value", raw_text)
        self.assertNotIn("very-secret-auth", raw_text)
        self.assertNotIn("very-secret-cookie", raw_text)
        self.assertNotIn("copy the whole repository", raw_text)
        self.assertLess(len(entry["raw"]["diff"]), 600)

    def test_reasonix_trace_recorder_maps_acp_messages(self) -> None:
        from scripts.ai_flow.trace import list_trace

        recorder = _TraceRecorder(
            run_dir=self.tmp,
            phase="write",
            agent="reasonix",
            env={"SECRET_TOKEN": "secret-token-value"},
        )
        recorder.sent("session/prompt", {"prompt": "secret-token-value"})
        recorder.stdout_json(
            {
                "jsonrpc": "2.0",
                "method": "session/request_permission",
                "id": 7,
                "params": {
                    "toolCall": {
                        "kind": "edit",
                        "title": "Edit file",
                        "rawInput": {"path": "src/app.py"},
                    }
                },
            }
        )
        recorder.stdout_json(
            {
                "jsonrpc": "2.0",
                "method": "session/update",
                "params": {"update": {"sessionUpdate": "agent_message_chunk", "content": "hello"}},
            }
        )
        recorder.stderr("warning secret-token-value")

        entries = list_trace(self.tmp)
        self.assertEqual(
            [entry["action"] for entry in entries],
            ["session/prompt", "session/request_permission", "session/update", "stderr"],
        )
        self.assertEqual(entries[1]["tool"], "edit")
        self.assertEqual(entries[1]["path"], "src/app.py")
        self.assertEqual(entries[1]["status"], "requested")
        self.assertEqual(entries[2]["detail"], "agent_message_chunk")
        self.assertNotIn("secret-token-value", json.dumps(entries))

    def test_reasonix_writer_accepts_fix_phase_for_trace_records(self) -> None:
        from scripts.ai_flow.adapters import run_reasonix_writer
        from scripts.ai_flow.trace import list_trace

        captured: dict[str, object] = {}

        def fake_run_acp(**kwargs: object) -> str:
            captured.update(kwargs)
            recorder = _TraceRecorder(
                run_dir=Path(kwargs["log_path"]).parent,
                phase=str(kwargs["phase"]),
                agent="reasonix",
            )
            recorder.stdout_json({"jsonrpc": "2.0", "method": "session/update", "params": {}})
            return "done"

        import scripts.ai_flow.adapters.reasonix_writer as reasonix_writer

        original_acp_command = reasonix_writer._acp_command
        original_run_acp = reasonix_writer._run_acp
        try:
            reasonix_writer._acp_command = lambda *args, **kwargs: ["reasonix", "acp"]  # type: ignore[assignment]
            reasonix_writer._run_acp = fake_run_acp  # type: ignore[assignment]
            run_reasonix_writer(
                prompt="repair",
                config={},
                cwd=self.tmp,
                log_path=self.tmp / "writer.log",
                phase="fix",
            )
        finally:
            reasonix_writer._acp_command = original_acp_command  # type: ignore[assignment]
            reasonix_writer._run_acp = original_run_acp  # type: ignore[assignment]

        self.assertEqual(captured["phase"], "fix")
        self.assertEqual(list_trace(self.tmp)[0]["phase"], "fix")

    def test_service_trace_returns_entries_and_total(self) -> None:
        from scripts.ai_flow.trace import append_trace

        root = self.tmp
        run_id = "run-trace"
        run_dir = root / ".ai" / "runs" / run_id
        run_dir.mkdir(parents=True)
        create_status(
            run_dir,
            run_id=run_id,
            task="trace service",
            repo_root=root,
            config_path=root / ".ai" / "patchbay.toml",
        )
        append_trace(run_dir, phase="write", action="stdout", status="ok")

        result = service.trace(root, run_id)

        self.assertEqual(result["run_id"], run_id)
        self.assertEqual(result["since"], 0)
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["returned"], 1)
        self.assertEqual(result["trace"][0]["action"], "stdout")

    def test_cli_and_mcp_expose_trace(self) -> None:
        from scripts.ai_flow import cli, mcp_server

        parser = cli.build_parser()
        args = parser.parse_args(["trace", "run-1", "--since", "2", "--phase", "write", "--json"])
        self.assertEqual(args.command, "trace")
        self.assertEqual(args.since, 2)
        self.assertEqual(args.phase, "write")

        response = mcp_server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        assert response is not None
        tools = {tool["name"]: tool for tool in response["result"]["tools"]}
        self.assertIn("patchbay_trace", tools)
        self.assertIn("ai_flow_trace", tools)
        self.assertIn("since", tools["patchbay_trace"]["inputSchema"]["properties"])
        self.assertIn("phase", tools["patchbay_trace"]["inputSchema"]["properties"])


if __name__ == "__main__":
    unittest.main()
