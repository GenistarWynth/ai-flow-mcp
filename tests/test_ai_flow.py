from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.ai_flow import git_utils, mcp_server, service
from scripts.ai_flow.adapters.claude_planner import (
    _claude_print_command,
    _extract_stream_json_error,
    _extract_stream_json_plan,
    _failure_detail,
    _is_retryable_connection_failure,
    _read_transcript_plan,
)
from scripts.ai_flow.adapters.codex_reviewer import _read_verdict_file
from scripts.ai_flow.adapters.reasonix_writer import _acp_command, _preferred_permission_option
from scripts.ai_flow.errors import SafetyError, StateError
from scripts.ai_flow.parsing import parse_planner_output, parse_writer_output
from scripts.ai_flow.plan_schema import empty_plan
from scripts.ai_flow.safety import validate_patch_safety
from scripts.ai_flow.runner import redact


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


class AiFlowTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = Path(tempfile.mkdtemp(prefix="ai-flow-test-"))
        self.repo = self.tempdir / "repo"
        self.repo.mkdir()
        self.script = PROJECT_ROOT / "scripts" / "ai-flow"
        run(["git", "init"], self.repo)
        run(["git", "config", "user.email", "ai-flow@example.test"], self.repo)
        run(["git", "config", "user.name", "ai-flow tests"], self.repo)
        (self.repo / "README.md").write_text("# Test Repo\n", encoding="utf-8")
        (self.repo / ".gitignore").write_text(".ai/runs/\n.ai/logs/\n.ai/worktrees/\n", encoding="utf-8")
        run(["git", "add", "README.md", ".gitignore"], self.repo)
        run(["git", "commit", "-m", "initial"], self.repo)

    def tearDown(self) -> None:
        shutil.rmtree(self.tempdir, ignore_errors=True)

    def cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return run(["python", str(self.script), *args], self.repo)

    def cli_json(self, *args: str) -> dict:
        completed = self.cli(*args, "--json")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return json.loads(completed.stdout)

    def create_planned_run(self) -> str:
        planned = self.cli_json("plan", "--task", "mock end to end", "--mock")
        return planned["run_id"]


class ParsingTests(unittest.TestCase):
    def test_claude_planner_uses_bare_plan_print_mode(self) -> None:
        command = _claude_print_command(["claude"], "plan this", "claude-opus-4-7")
        self.assertEqual(command[:3], ["claude", "-p", "plan this"])
        self.assertIn("--permission-mode", command)
        self.assertIn("plan", command)
        self.assertIn("--bare", command)
        self.assertIn("--output-format", command)
        self.assertIn("stream-json", command)
        self.assertIn("--verbose", command)

    def test_claude_failure_detail_prefers_first_stdout_line(self) -> None:
        detail = _failure_detail("API Error: Unable to connect to API (ConnectionRefused)\nmore", "")
        self.assertEqual(detail, "API Error: Unable to connect to API (ConnectionRefused)")

    def test_claude_stream_json_error_reads_result_error(self) -> None:
        output = "\n".join(
            [
                json.dumps({"type": "system", "subtype": "init"}),
                json.dumps({"type": "result", "is_error": True, "result": "API Error: Unable to connect to API (ConnectionRefused)"}),
            ]
        )
        self.assertEqual(
            _extract_stream_json_error(output),
            "API Error: Unable to connect to API (ConnectionRefused)",
        )
        self.assertTrue(_is_retryable_connection_failure(output, ""))

    def test_claude_stream_json_plan_reads_assistant_text_when_result_empty(self) -> None:
        text = "BEGIN_AI_FLOW_PLAN_JSON\n{}\nEND_AI_FLOW_PLAN_JSON\n\n# Plan"
        output = "\n".join(
            [
                json.dumps({"type": "system", "subtype": "init"}),
                json.dumps(
                    {
                        "type": "assistant",
                        "message": {
                            "content": [
                                {"type": "thinking", "thinking": "hidden"},
                                {"type": "text", "text": text},
                            ]
                        },
                    }
                ),
                json.dumps({"type": "result", "result": ""}),
            ]
        )
        self.assertEqual(_extract_stream_json_plan(output), text)

    def test_claude_transcript_plan_fallback_reads_assistant_text(self) -> None:
        path = Path(tempfile.mkdtemp(prefix="ai-flow-transcript-")) / "session.jsonl"
        try:
            marker = "E:/repo/.ai/runs/current/claude-planner.prompt.md"
            text = "BEGIN_AI_FLOW_PLAN_JSON\n{}\nEND_AI_FLOW_PLAN_JSON\n\n# Plan"
            path.write_text(
                "\n".join(
                    [
                        json.dumps({"type": "user", "message": {"content": f"Read {marker}"}}),
                        json.dumps(
                            {
                                "type": "assistant",
                                "message": {
                                    "content": [
                                        {"type": "thinking", "thinking": "hidden"},
                                        {"type": "text", "text": text},
                                    ]
                                },
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            self.assertEqual(_read_transcript_plan(path, prompt_marker=marker), text)
            self.assertIsNone(_read_transcript_plan(path, prompt_marker="other-run"))
        finally:
            shutil.rmtree(path.parent, ignore_errors=True)

    def test_plan_json_parses(self) -> None:
        plan = empty_plan("parse")
        raw = "BEGIN_AI_FLOW_PLAN_JSON\n" + json.dumps(plan) + "\nEND_AI_FLOW_PLAN_JSON\n\n# Plan\n"
        parsed = parse_planner_output(raw)
        self.assertEqual(parsed.plan_json["version"], 1)
        self.assertIn("# Plan", parsed.markdown)

    def test_writer_diff_parses(self) -> None:
        raw = """BEGIN_WRITER_SUMMARY
done
END_WRITER_SUMMARY

BEGIN_DIFF
diff --git a/a.txt b/a.txt
new file mode 100644
--- /dev/null
+++ b/a.txt
@@ -0,0 +1 @@
+hello
END_DIFF
"""
        parsed = parse_writer_output(raw)
        self.assertEqual(parsed.summary, "done")
        self.assertIn("diff --git", parsed.diff or "")

    def test_codex_reviewer_detects_complete_verdict_file(self) -> None:
        tempdir = Path(tempfile.mkdtemp(prefix="ai-flow-codex-output-"))
        try:
            output = tempdir / "codex-reviewer.output.md"
            output.write_text("PASS\n\nSummary:\nDone.\n", encoding="utf-8")
            self.assertTrue(_read_verdict_file(output).startswith("PASS"))
            output.write_text("Thinking...\n", encoding="utf-8")
            self.assertEqual(_read_verdict_file(output), "")
        finally:
            shutil.rmtree(tempdir, ignore_errors=True)

    def test_reasonix_acp_command_uses_agent_entrypoint(self) -> None:
        command = _acp_command(
            {
                "commands": {"reasonix": "reasonix.cmd run --preset pro"},
                "models": {"writer": "deepseek-v4-pro"},
            },
            Path("C:/repo"),
            Path("writer.log"),
        )
        self.assertEqual(command[:2], ["reasonix.cmd", "acp"])
        self.assertNotIn("--yolo", command)
        self.assertNotIn("run", command)

    def test_reasonix_permission_prefers_allow_once(self) -> None:
        option = _preferred_permission_option(
            [
                {"optionId": "reject"},
                {"optionId": "allow_once"},
            ]
        )
        self.assertEqual(option, "allow_once")

    def test_reasonix_permission_rejects_execute(self) -> None:
        option = _preferred_permission_option(
            {
                "toolCall": {"kind": "execute"},
                "options": [
                    {"optionId": "allow_once"},
                    {"optionId": "reject"},
                ],
            }
        )
        self.assertEqual(option, "reject")

    def test_reasonix_permission_rejects_unsafe_edit_path(self) -> None:
        option = _preferred_permission_option(
            {
                "toolCall": {
                    "kind": "edit",
                    "title": "write_file",
                    "rawInput": {"path": "../outside.txt", "content": "bad"},
                },
                "options": [
                    {"optionId": "allow_once"},
                    {"optionId": "reject"},
                ],
            }
        )
        self.assertEqual(option, "reject")

    def test_reasonix_permission_allows_safe_edit_path(self) -> None:
        option = _preferred_permission_option(
            {
                "toolCall": {
                    "kind": "edit",
                    "title": "write_file",
                    "rawInput": {"path": "docs/safe.md", "content": "ok"},
                },
                "options": [
                    {"optionId": "reject"},
                    {"optionId": "allow_once"},
                ],
            }
        )
        self.assertEqual(option, "allow_once")

    def test_reasonix_permission_rejects_unknown_tool_call(self) -> None:
        option = _preferred_permission_option(
            {
                "toolCall": {"kind": "mystery", "title": "unknown_tool", "rawInput": {}},
                "options": [
                    {"optionId": "allow_once"},
                    {"optionId": "reject"},
                ],
            }
        )
        self.assertEqual(option, "reject")

    def test_redact_accepts_extra_sensitive_values(self) -> None:
        text = redact("api said sensitive-token-value is invalid", extra_values=["sensitive-token-value"])
        self.assertNotIn("sensitive-token-value", text)
        self.assertIn("***REDACTED***", text)


class McpServerTests(unittest.TestCase):
    def test_initialize_and_tools_list(self) -> None:
        init = mcp_server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        self.assertEqual(init["result"]["serverInfo"]["name"], "ai-flow")
        tools = mcp_server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        names = {tool["name"] for tool in tools["result"]["tools"]}
        for name in (
            "ai_flow_plan",
            "ai_flow_approve",
            "ai_flow_write",
            "ai_flow_test",
            "ai_flow_review",
            "ai_flow_fix",
            "ai_flow_status",
            "ai_flow_diff",
            "ai_flow_apply",
        ):
            self.assertIn(name, names)

    def test_tools_call_wraps_result_as_text_content(self) -> None:
        original = dict(mcp_server.TOOLS)
        try:
            mcp_server.TOOLS["ai_flow_status"] = lambda run_id: {"run_id": run_id, "status": "OK"}
            response = mcp_server.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {"name": "ai_flow_status", "arguments": {"run_id": "r1"}},
                }
            )
            payload = json.loads(response["result"]["content"][0]["text"])
            self.assertEqual(payload, {"run_id": "r1", "status": "OK"})
        finally:
            mcp_server.TOOLS.clear()
            mcp_server.TOOLS.update(original)

    def test_unknown_tool_returns_json_rpc_error(self) -> None:
        response = mcp_server.handle(
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {"name": "missing", "arguments": {}},
            }
        )
        self.assertEqual(response["error"]["code"], -32601)

    def test_tool_exception_returns_mcp_error_content(self) -> None:
        original = dict(mcp_server.TOOLS)
        try:
            def boom(run_id: str) -> dict:
                raise RuntimeError(f"bad run {run_id}")

            mcp_server.TOOLS["ai_flow_status"] = boom
            response = mcp_server.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 5,
                    "method": "tools/call",
                    "params": {"name": "ai_flow_status", "arguments": {"run_id": "r2"}},
                }
            )
            self.assertTrue(response["result"]["isError"])
            self.assertIn("bad run r2", response["result"]["content"][0]["text"])
        finally:
            mcp_server.TOOLS.clear()
            mcp_server.TOOLS.update(original)


class WorkflowTests(AiFlowTestCase):
    def test_status_transitions_and_artifacts(self) -> None:
        run_id = self.create_planned_run()
        status = self.cli_json("status", run_id)
        self.assertEqual(status["status"], "PLANNED")
        write_before_approval = self.cli("write", run_id, "--mock")
        self.assertNotEqual(write_before_approval.returncode, 0)
        run_id = self.create_planned_run()
        self.cli_json("approve", run_id)
        self.cli_json("write", run_id, "--mock")
        self.cli_json("test", run_id)
        self.cli_json("review", run_id, "--mock")
        status = self.cli_json("status", run_id)
        self.assertEqual(status["status"], "REVIEWED_PASS")
        for name in ("TASK.md", "PLAN.md", "plan.json", "APPROVAL.json", "STATUS.json", "WORKTREE_PATH", "BASE_COMMIT", "IMPLEMENTATION.md", "FINAL.diff", "TEST.log", "REVIEW.md", "FIXES.md", "claude-planner.log", "writer.log", "codex-reviewer.log", "git.log"):
            self.assertIn(name, status["artifacts"])

    def test_mock_full_flow_can_apply(self) -> None:
        run_id = self.create_planned_run()
        self.cli_json("approve", run_id)
        self.cli_json("write", run_id, "--mock")
        self.cli_json("test", run_id)
        self.cli_json("review", run_id, "--mock")
        self.cli_json("apply", run_id)
        self.assertTrue((self.repo / "AI_FLOW_MOCK_OUTPUT.md").exists())

    def test_worktree_creation_failure_records_error(self) -> None:
        run_id = self.create_planned_run()
        self.cli_json("approve", run_id)
        cfg = self.repo / ".ai" / "ai-flow.toml"
        cfg.write_text(
            """[workflow]
worktree_root = ".ai/preexisting"
default_branch_prefix = "ai-flow"
fail_on_dirty_workspace = true

[commands_allowlist]
test = []
""",
            encoding="utf-8",
        )
        worktree_path = self.repo / ".ai" / "preexisting" / run_id
        worktree_path.mkdir(parents=True)
        failed = self.cli("write", run_id, "--mock")
        self.assertNotEqual(failed.returncode, 0)
        status = self.cli_json("status", run_id)
        self.assertEqual(status["status"], "FAILED")
        self.assertEqual(status["stage"], "write")

    def test_writer_scope_rejects_unexplained_file_outside_plan(self) -> None:
        run_id = self.create_planned_run()
        run_path = self.repo / ".ai" / "runs" / run_id
        unexpected_diff = """diff --git a/OTHER.md b/OTHER.md
new file mode 100644
--- /dev/null
+++ b/OTHER.md
@@ -0,0 +1 @@
+outside
"""
        with self.assertRaises(SafetyError):
            service._validate_writer_scope(run_path, unexpected_diff, "Created only the planned file.")

    def test_writer_scope_allows_explained_file_outside_plan(self) -> None:
        run_id = self.create_planned_run()
        run_path = self.repo / ".ai" / "runs" / run_id
        unexpected_diff = """diff --git a/OTHER.md b/OTHER.md
new file mode 100644
--- /dev/null
+++ b/OTHER.md
@@ -0,0 +1 @@
+outside
"""
        service._validate_writer_scope(run_path, unexpected_diff, "Created OTHER.md because the approved implementation needed a fixture.")

    def test_writer_scope_allows_prior_fix_explanation(self) -> None:
        run_id = self.create_planned_run()
        run_path = self.repo / ".ai" / "runs" / run_id
        (run_path / "FIXES.md").write_text("## Fix iteration 1\n\nCreated OTHER.md as a repair artifact.\n", encoding="utf-8")
        unexpected_diff = """diff --git a/OTHER.md b/OTHER.md
new file mode 100644
--- /dev/null
+++ b/OTHER.md
@@ -0,0 +1 @@
+outside
"""
        service._validate_writer_scope(run_path, unexpected_diff, "Second repair touched only current files.")

    def test_plan_read_only_check_rejects_non_artifact_workspace_change(self) -> None:
        run_id = self.create_planned_run()
        run_path = self.repo / ".ai" / "runs" / run_id
        before = service._workspace_snapshot(self.repo)
        (self.repo / "planner-side-effect.txt").write_text("bad\n", encoding="utf-8")
        with self.assertRaises(SafetyError):
            service._assert_plan_read_only(self.repo, run_path, before)

    def test_illegal_path_patch_rejected(self) -> None:
        bad = """diff --git a/../x b/../x
--- a/../x
+++ b/../x
@@ -0,0 +1 @@
+bad
"""
        with self.assertRaises(SafetyError):
            validate_patch_safety(bad)

    def test_reviewer_modification_detection(self) -> None:
        run_id = self.create_planned_run()
        self.cli_json("approve", run_id)
        self.cli_json("write", run_id, "--mock")
        self.cli_json("test", run_id)
        run_path = self.repo / ".ai" / "runs" / run_id
        status = json.loads((run_path / "STATUS.json").read_text(encoding="utf-8"))
        worktree = Path(status["worktree_path"])
        before = git_utils.diff(worktree)
        (worktree / "REVIEW_SIDE_EFFECT.txt").write_text("bad\n", encoding="utf-8")
        run(["git", "add", "REVIEW_SIDE_EFFECT.txt"], worktree)
        after = git_utils.diff(worktree)
        self.assertNotEqual(before, after)

    def test_test_command_allowlist(self) -> None:
        run_id = self.create_planned_run()
        run_path = self.repo / ".ai" / "runs" / run_id
        plan_path = run_path / "plan.json"
        data = json.loads(plan_path.read_text(encoding="utf-8"))
        data["test_commands"] = ["python -c \"print('not allowed')\""]
        plan_path.write_text(json.dumps(data), encoding="utf-8")
        self.cli_json("approve", run_id)
        self.cli_json("write", run_id, "--mock")
        result = self.cli("test", run_id)
        self.assertNotEqual(result.returncode, 0)
        status = self.cli_json("status", run_id)
        self.assertEqual(status["status"], "FAILED")
        self.assertEqual(status["stage"], "test")

    def test_fix_loop_max_two(self) -> None:
        run_id = self.create_planned_run()
        self.cli_json("approve", run_id)
        self.cli_json("write", run_id, "--mock")
        self.cli_json("test", run_id)
        run_path = self.repo / ".ai" / "runs" / run_id
        (run_path / "REVIEW.md").write_text("CHANGES_REQUESTED\n\nRequired Fixes:\n1. Test.\n", encoding="utf-8")
        status = json.loads((run_path / "STATUS.json").read_text(encoding="utf-8"))
        status["status"] = "REVIEWED_CHANGES_REQUESTED"
        (run_path / "STATUS.json").write_text(json.dumps(status), encoding="utf-8")
        self.cli_json("fix", run_id, "--mock")
        self.cli_json("test", run_id)
        status = json.loads((run_path / "STATUS.json").read_text(encoding="utf-8"))
        status["status"] = "REVIEWED_CHANGES_REQUESTED"
        (run_path / "STATUS.json").write_text(json.dumps(status), encoding="utf-8")
        self.cli_json("fix", run_id, "--mock")
        status = json.loads((run_path / "STATUS.json").read_text(encoding="utf-8"))
        status["status"] = "REVIEWED_CHANGES_REQUESTED"
        (run_path / "STATUS.json").write_text(json.dumps(status), encoding="utf-8")
        third = self.cli("fix", run_id, "--mock")
        self.assertNotEqual(third.returncode, 0)

    def test_dirty_workspace_apply_fails(self) -> None:
        run_id = self.create_planned_run()
        self.cli_json("approve", run_id)
        self.cli_json("write", run_id, "--mock")
        self.cli_json("test", run_id)
        self.cli_json("review", run_id, "--mock")
        (self.repo / "dirty.txt").write_text("dirty\n", encoding="utf-8")
        result = self.cli("apply", run_id)
        self.assertNotEqual(result.returncode, 0)
        status = self.cli_json("status", run_id)
        self.assertEqual(status["status"], "FAILED")
        self.assertEqual(status["stage"], "git")

    def test_review_can_recover_cached_output_after_timeout_failure(self) -> None:
        run_id = self.create_planned_run()
        self.cli_json("approve", run_id)
        self.cli_json("write", run_id, "--mock")
        self.cli_json("test", run_id)
        run_path = self.repo / ".ai" / "runs" / run_id
        (run_path / "codex-reviewer.output.md").write_text("PASS\n\nSummary:\nRecovered.\n", encoding="utf-8")
        status = json.loads((run_path / "STATUS.json").read_text(encoding="utf-8"))
        status["status"] = "FAILED"
        status["stage"] = "review"
        status["error"] = "outer timeout"
        (run_path / "STATUS.json").write_text(json.dumps(status), encoding="utf-8")
        recovered = self.cli_json("review", run_id)
        self.assertEqual(recovered["status"], "REVIEWED_PASS")
        self.assertEqual(recovered["review_result"], "PASS")
        self.assertIn("Recovered", (run_path / "REVIEW.md").read_text(encoding="utf-8"))

    def test_review_can_recover_cached_output_from_reviewing_status(self) -> None:
        run_id = self.create_planned_run()
        self.cli_json("approve", run_id)
        self.cli_json("write", run_id, "--mock")
        self.cli_json("test", run_id)
        run_path = self.repo / ".ai" / "runs" / run_id
        (run_path / "codex-reviewer.output.md").write_text("PASS\n\nSummary:\nRecovered from in-flight review.\n", encoding="utf-8")
        status = json.loads((run_path / "STATUS.json").read_text(encoding="utf-8"))
        status["status"] = "REVIEWING"
        (run_path / "STATUS.json").write_text(json.dumps(status), encoding="utf-8")
        recovered = self.cli_json("review", run_id)
        self.assertEqual(recovered["status"], "REVIEWED_PASS")
        self.assertIn("in-flight", (run_path / "REVIEW.md").read_text(encoding="utf-8"))

    def test_review_cached_recovery_detects_worktree_modification(self) -> None:
        run_id = self.create_planned_run()
        self.cli_json("approve", run_id)
        self.cli_json("write", run_id, "--mock")
        self.cli_json("test", run_id)
        run_path = self.repo / ".ai" / "runs" / run_id
        (run_path / "codex-reviewer.output.md").write_text("PASS\n\nSummary:\nCached.\n", encoding="utf-8")
        status = json.loads((run_path / "STATUS.json").read_text(encoding="utf-8"))
        worktree = Path(status["worktree_path"])
        (worktree / "REVIEW_SIDE_EFFECT.txt").write_text("bad\n", encoding="utf-8")
        status["status"] = "REVIEWING"
        (run_path / "STATUS.json").write_text(json.dumps(status), encoding="utf-8")
        result = self.cli("review", run_id)
        self.assertNotEqual(result.returncode, 0)
        failed = self.cli_json("status", run_id)
        self.assertEqual(failed["status"], "FAILED")
        self.assertEqual(failed["stage"], "review")

    def test_review_can_retry_after_transient_git_failure(self) -> None:
        run_id = self.create_planned_run()
        self.cli_json("approve", run_id)
        self.cli_json("write", run_id, "--mock")
        self.cli_json("test", run_id)
        run_path = self.repo / ".ai" / "runs" / run_id
        status = json.loads((run_path / "STATUS.json").read_text(encoding="utf-8"))
        status["status"] = "FAILED"
        status["stage"] = "git"
        status["error"] = "temporary git access failure"
        (run_path / "STATUS.json").write_text(json.dumps(status), encoding="utf-8")
        reviewed = self.cli_json("review", run_id, "--mock")
        self.assertEqual(reviewed["status"], "REVIEWED_PASS")


if __name__ == "__main__":
    unittest.main()
