from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
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
from scripts.ai_flow.adapters.cli_planner import extract_plain_stdout_plan
from scripts.ai_flow.adapters.codex_planner import _codex_exec_command
from scripts.ai_flow.adapters.codex_reviewer import _read_verdict_file
from scripts.ai_flow.adapters.cli_reviewer import extract_reviewer_output
from scripts.ai_flow.adapters.reasonix_writer import _acp_command, _preferred_permission_option
from scripts.ai_flow.config import load_config, resolve_phase
from scripts.ai_flow.errors import AiFlowError, SafetyError, StateError
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
        self.tempdir = Path(tempfile.mkdtemp(prefix="patchbay-test-"))
        self.repo = self.tempdir / "repo"
        self.repo.mkdir()
        self.script = PROJECT_ROOT / "scripts" / "patchbay"
        run(["git", "init"], self.repo)
        run(["git", "config", "user.email", "patchbay@example.test"], self.repo)
        run(["git", "config", "user.name", "Patchbay tests"], self.repo)
        (self.repo / "README.md").write_text("# Test Repo\n", encoding="utf-8")
        (self.repo / ".gitignore").write_text(
            ".ai/runs/\n.ai/logs/\n.ai/worktrees/\n.ai/patchbay.toml\n.patchbay-worktrees/\n",
            encoding="utf-8",
        )
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

    def allow_apply_without_tests(self) -> None:
        path = self.repo / ".ai" / "patchbay.toml"
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        if "[workflow]" in existing:
            text = existing + "\nallow_apply_without_tests = true\n"
        else:
            text = existing + "\n[workflow]\nallow_apply_without_tests = true\n"
        path.write_text(text, encoding="utf-8")


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

    def test_codex_planner_uses_prompt_argument_not_profile_flag(self) -> None:
        command = _codex_exec_command(["codex"], "plan this", "gpt-5.5")
        self.assertEqual(command[:2], ["codex", "exec"])
        self.assertNotIn("-p", command)
        self.assertIn("--sandbox", command)
        self.assertIn("read-only", command)
        self.assertIn("--model", command)
        self.assertEqual(command[-1], "plan this")

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

    def test_cli_planner_extracts_plain_stdout_plan(self) -> None:
        raw = "intro\nBEGIN_AI_FLOW_PLAN_JSON\n{}\nEND_AI_FLOW_PLAN_JSON\n\n# Plan\n"
        self.assertEqual(
            extract_plain_stdout_plan(raw),
            "BEGIN_AI_FLOW_PLAN_JSON\n{}\nEND_AI_FLOW_PLAN_JSON\n\n# Plan",
        )

    def test_claude_transcript_plan_fallback_reads_assistant_text(self) -> None:
        path = Path(tempfile.mkdtemp(prefix="patchbay-transcript-")) / "session.jsonl"
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
        tempdir = Path(tempfile.mkdtemp(prefix="patchbay-codex-output-"))
        try:
            output = tempdir / "codex-reviewer.output.md"
            output.write_text("PASS\n\nSummary:\nDone.\n", encoding="utf-8")
            self.assertTrue(_read_verdict_file(output).startswith("PASS"))
            output.write_text("Thinking...\n", encoding="utf-8")
            self.assertEqual(_read_verdict_file(output), "")
        finally:
            shutil.rmtree(tempdir, ignore_errors=True)

    def test_cli_reviewer_extracts_plain_stdout_verdict(self) -> None:
        output = "PASS\n\nSummary:\nDone via stdout.\n"
        self.assertEqual(extract_reviewer_output(output), output.strip())

    def test_cli_reviewer_extracts_stream_json_verdict(self) -> None:
        verdict = "CHANGES_REQUESTED\n\nBlocking Issues:\n1. Needs work.\n"
        output = "\n".join(
            [
                json.dumps({"type": "system", "subtype": "init"}),
                json.dumps(
                    {
                        "type": "assistant",
                        "message": {
                            "content": [
                                {"type": "thinking", "thinking": "hidden"},
                                {"type": "text", "text": verdict},
                            ]
                        },
                    }
                ),
            ]
        )
        self.assertEqual(extract_reviewer_output(output), verdict.strip())

    def test_generic_cli_reviewer_uses_stdout_without_verdict_file(self) -> None:
        from scripts.ai_flow.adapters.cli_reviewer import run_generic_cli_reviewer

        tempdir = Path(tempfile.mkdtemp(prefix="patchbay-reviewer-stdout-"))
        try:
            log_path = tempdir / "reviewer.log"

            def build_argv(*, command: list[str], prompt: str, model: str, output_file: str) -> list[str]:
                self.assertTrue(output_file.endswith("fake-reviewer.output.md"))
                return [
                    *command,
                    "-c",
                    "print('PASS\\n\\nSummary:\\nstdout reviewer passed.')",
                ]

            output = run_generic_cli_reviewer(
                prompt="review this",
                config={"commands": {"fake": sys.executable}},
                cwd=tempdir,
                log_path=log_path,
                command_key="fake",
                model="fake-model",
                build_argv=build_argv,
                expect_output_file=False,
            )

            self.assertTrue(output.startswith("PASS"))
            self.assertFalse((tempdir / "fake-reviewer.output.md").exists())
        finally:
            shutil.rmtree(tempdir, ignore_errors=True)

    def test_claude_and_gemini_reviewer_use_prompt_file_directive(self) -> None:
        from scripts.ai_flow.adapters.claude_reviewer import run_claude_reviewer
        from scripts.ai_flow.adapters.gemini_reviewer import run_gemini_reviewer

        tempdir = Path(tempfile.mkdtemp(prefix="patchbay-reviewer-prompt-file-"))
        try:
            long_prompt = "review prompt " + ("x" * 10000)
            for provider, command_key, runner in (
                ("claude", "claude", run_claude_reviewer),
                ("gemini", "gemini", run_gemini_reviewer),
            ):
                with self.subTest(provider=provider):
                    with mock.patch(
                        f"scripts.ai_flow.adapters.{provider}_reviewer.run_generic_cli_reviewer",
                        return_value="PASS\n\nSummary:\nok\n",
                    ) as generic:
                        runner(
                            prompt=long_prompt,
                            config={"commands": {command_key: command_key}, "models": {"reviewer": "test-model"}},
                            cwd=tempdir,
                            log_path=tempdir / f"{command_key}-reviewer.log",
                        )
                    kwargs = generic.call_args.kwargs
                    directive = kwargs["prompt"]
                    self.assertIn(f"{command_key}-reviewer.prompt.md", directive)
                    self.assertNotIn(long_prompt, directive)
                    self.assertFalse(kwargs["send_stdin"])
                    prompt_file = tempdir / f"{command_key}-reviewer.prompt.md"
                    self.assertEqual(prompt_file.read_text(encoding="utf-8"), long_prompt)
                    argv = kwargs["build_argv"](
                        command=[command_key],
                        prompt=directive,
                        model="test-model",
                        output_file=str(tempdir / "out.md"),
                    )
                    self.assertNotIn(long_prompt, " ".join(argv))
        finally:
            shutil.rmtree(tempdir, ignore_errors=True)

    def test_generic_cli_reviewer_ignores_stale_output_file_for_stdout_provider(self) -> None:
        from scripts.ai_flow.adapters.cli_reviewer import run_generic_cli_reviewer

        tempdir = Path(tempfile.mkdtemp(prefix="patchbay-reviewer-stale-"))
        try:
            log_path = tempdir / "reviewer.log"
            (tempdir / "fake-reviewer.output.md").write_text("PASS\n\nSummary:\nstale file.\n", encoding="utf-8")

            def build_argv(*, command: list[str], prompt: str, model: str, output_file: str) -> list[str]:
                return [
                    *command,
                    "-c",
                    "import time; time.sleep(2); print('CHANGES_REQUESTED\\n\\nBlocking Issues:\\n1. stdout reviewer ran.')",
                ]

            output = run_generic_cli_reviewer(
                prompt="review this",
                config={"commands": {"fake": sys.executable}},
                cwd=tempdir,
                log_path=log_path,
                command_key="fake",
                model="fake-model",
                build_argv=build_argv,
                expect_output_file=False,
            )

            self.assertTrue(output.startswith("CHANGES_REQUESTED"))
            self.assertIn("stdout reviewer ran", output)
        finally:
            shutil.rmtree(tempdir, ignore_errors=True)

    def test_generic_cli_reviewer_does_not_poll_output_file_for_stdout_provider(self) -> None:
        from scripts.ai_flow.adapters.cli_reviewer import run_generic_cli_reviewer

        tempdir = Path(tempfile.mkdtemp(prefix="patchbay-reviewer-no-poll-"))
        try:
            log_path = tempdir / "reviewer.log"

            def build_argv(*, command: list[str], prompt: str, model: str, output_file: str) -> list[str]:
                return [
                    *command,
                    "-c",
                    "print('PASS\\n\\nSummary:\\nstdout reviewer passed.')",
                ]

            with mock.patch(
                "scripts.ai_flow.adapters.cli_reviewer.read_verdict_file",
                side_effect=AssertionError("stdout-only reviewer should not poll verdict files"),
            ):
                output = run_generic_cli_reviewer(
                    prompt="review this",
                    config={"commands": {"fake": sys.executable}},
                    cwd=tempdir,
                    log_path=log_path,
                    command_key="fake",
                    model="fake-model",
                    build_argv=build_argv,
                    expect_output_file=False,
                )

            self.assertTrue(output.startswith("PASS"))
        finally:
            shutil.rmtree(tempdir, ignore_errors=True)

    def test_generic_cli_reviewer_rejects_verdict_file_when_process_fails(self) -> None:
        from scripts.ai_flow.adapters.cli_reviewer import run_generic_cli_reviewer

        tempdir = Path(tempfile.mkdtemp(prefix="patchbay-reviewer-file-fail-"))
        try:
            log_path = tempdir / "reviewer.log"

            def build_argv(*, command: list[str], prompt: str, model: str, output_file: str) -> list[str]:
                script = (
                    "from pathlib import Path; import sys; "
                    f"Path({output_file!r}).write_text('PASS\\n\\nSummary:\\nearly file.\\n', encoding='utf-8'); "
                    "sys.exit(7)"
                )
                return [*command, "-c", script]

            with self.assertRaises(AiFlowError):
                run_generic_cli_reviewer(
                    prompt="review this",
                    config={"commands": {"fake": sys.executable}},
                    cwd=tempdir,
                    log_path=log_path,
                    command_key="fake",
                    model="fake-model",
                    build_argv=build_argv,
                )
        finally:
            shutil.rmtree(tempdir, ignore_errors=True)

    def test_codex_reviewer_rejects_malformed_stdout(self) -> None:
        from scripts.ai_flow.adapters.codex_reviewer import run_codex_reviewer

        class FakeResult:
            returncode = 0
            stdout = "not a review verdict"
            stderr = ""

        tempdir = Path(tempfile.mkdtemp(prefix="patchbay-codex-reviewer-bad-"))
        try:
            with mock.patch(
                "scripts.ai_flow.adapters.codex_reviewer.run_cli_until_verdict",
                return_value=FakeResult(),
            ):
                with self.assertRaises(AiFlowError):
                    run_codex_reviewer(
                        prompt="review",
                        config={"commands": {"codex": "codex"}, "models": {"reviewer": "gpt-test"}},
                        cwd=tempdir,
                        log_path=tempdir / "reviewer.log",
                    )
        finally:
            shutil.rmtree(tempdir, ignore_errors=True)

    def test_cli_reviewer_sparse_env_keeps_parent_path(self) -> None:
        from scripts.ai_flow.adapters.cli_reviewer import run_generic_cli_reviewer

        tempdir = Path(tempfile.mkdtemp(prefix="patchbay-reviewer-env-"))
        try:
            log_path = tempdir / "reviewer.log"

            def build_argv(*, command: list[str], prompt: str, model: str, output_file: str) -> list[str]:
                return [
                    *command,
                    "-c",
                    "import os; print('PASS\\n\\nSummary:\\nPATH=' + str(bool(os.environ.get('PATH'))) + ';CUSTOM=' + os.environ.get('PATCHBAY_CUSTOM_ENV', ''))",
                ]

            output = run_generic_cli_reviewer(
                prompt="review this",
                config={"commands": {"fake": sys.executable}},
                cwd=tempdir,
                log_path=log_path,
                command_key="fake",
                model="fake-model",
                build_argv=build_argv,
                env={"PATCHBAY_CUSTOM_ENV": "yes"},
                expect_output_file=False,
            )

            self.assertIn("PATH=True", output)
            self.assertIn("CUSTOM=yes", output)
        finally:
            shutil.rmtree(tempdir, ignore_errors=True)

    def test_cli_reviewer_redacts_phase_env_from_logs(self) -> None:
        from scripts.ai_flow.adapters.cli_reviewer import run_generic_cli_reviewer

        tempdir = Path(tempfile.mkdtemp(prefix="patchbay-reviewer-redact-"))
        try:
            log_path = tempdir / "reviewer.log"
            secret = "phase-secret-token"

            def build_argv(*, command: list[str], prompt: str, model: str, output_file: str) -> list[str]:
                return [
                    *command,
                    "-c",
                    "import os; print('PASS\\n\\nSummary:\\n' + os.environ['PATCHBAY_SECRET_TOKEN'])",
                ]

            run_generic_cli_reviewer(
                prompt="review this",
                config={"commands": {"fake": sys.executable}},
                cwd=tempdir,
                log_path=log_path,
                command_key="fake",
                model="fake-model",
                build_argv=build_argv,
                env={"PATCHBAY_SECRET_TOKEN": secret},
                expect_output_file=False,
            )

            log_text = log_path.read_text(encoding="utf-8")
            self.assertNotIn(secret, log_text)
            self.assertIn("***REDACTED***", log_text)
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
        self.assertEqual(init["result"]["serverInfo"]["name"], "patchbay")
        tools = mcp_server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        names = {tool["name"] for tool in tools["result"]["tools"]}
        for name in (
            "patchbay_plan",
            "patchbay_approve",
            "patchbay_write",
            "patchbay_test",
            "patchbay_review",
            "patchbay_fix",
            "patchbay_status",
            "patchbay_diff",
            "patchbay_apply",
        ):
            self.assertIn(name, names)
        for name in ("ai_flow_plan", "ai_flow_status", "ai_flow_apply"):
            self.assertIn(name, names)

    def test_tools_call_wraps_result_as_text_content(self) -> None:
        original = dict(mcp_server.TOOLS)
        try:
            mcp_server.TOOLS["patchbay_status"] = lambda run_id: {"run_id": run_id, "status": "OK"}
            response = mcp_server.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {"name": "patchbay_status", "arguments": {"run_id": "r1"}},
                }
            )
            payload = json.loads(response["result"]["content"][0]["text"])
            self.assertEqual(payload, {"run_id": "r1", "status": "OK"})
        finally:
            mcp_server.TOOLS.clear()
            mcp_server.TOOLS.update(original)

    def test_legacy_tool_alias_still_calls_canonical_handler(self) -> None:
        original = dict(mcp_server.TOOLS)
        try:
            mcp_server.TOOLS["ai_flow_status"] = lambda run_id: {"run_id": run_id, "status": "OK"}
            response = mcp_server.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 6,
                    "method": "tools/call",
                    "params": {"name": "ai_flow_status", "arguments": {"run_id": "legacy"}},
                }
            )
            payload = json.loads(response["result"]["content"][0]["text"])
            self.assertEqual(payload, {"run_id": "legacy", "status": "OK"})
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

            mcp_server.TOOLS["patchbay_status"] = boom
            response = mcp_server.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 5,
                    "method": "tools/call",
                    "params": {"name": "patchbay_status", "arguments": {"run_id": "r2"}},
                }
            )
            self.assertTrue(response["result"]["isError"])
            self.assertIn("bad run r2", response["result"]["content"][0]["text"])
        finally:
            mcp_server.TOOLS.clear()
            mcp_server.TOOLS.update(original)


class WorkflowTests(AiFlowTestCase):
    def test_legacy_config_name_is_still_loaded(self) -> None:
        legacy = self.repo / ".ai" / "ai-flow.toml"
        legacy.parent.mkdir(parents=True, exist_ok=True)
        legacy.write_text(
            """[workflow]
default_branch_prefix = "legacy-prefix"
""",
            encoding="utf-8",
        )
        cfg = load_config(self.repo)
        self.assertEqual(cfg["workflow"]["default_branch_prefix"], "legacy-prefix")

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
        self.allow_apply_without_tests()
        run_id = self.create_planned_run()
        self.cli_json("approve", run_id)
        self.cli_json("write", run_id, "--mock")
        self.cli_json("test", run_id)
        self.cli_json("review", run_id, "--mock")
        self.cli_json("apply", run_id)
        self.assertTrue((self.repo / "PATCHBAY_MOCK_OUTPUT.md").exists())

    def test_no_test_commands_do_not_allow_apply_by_default(self) -> None:
        run_id = self.create_planned_run()
        self.cli_json("approve", run_id)
        self.cli_json("write", run_id, "--mock")
        tested = self.cli_json("test", run_id)
        self.assertFalse(tested["tests_passed"])
        self.assertEqual(tested["tests_status"], "SKIPPED")
        self.cli_json("review", run_id, "--mock")
        status = self.cli_json("status", run_id)
        self.assertFalse(status["gate_state"]["ready_to_apply"])
        self.assertEqual(status["gate_state"]["tests_status"], "SKIPPED")

        result = self.cli("apply", run_id)

        self.assertNotEqual(result.returncode, 0)
        failed = self.cli_json("status", run_id)
        self.assertEqual(failed["status"], "FAILED")
        self.assertEqual(failed["stage"], "apply")
        self.assertIn("tests_passed is false", failed["error"])

    def test_worktree_creation_failure_records_error(self) -> None:
        run_id = self.create_planned_run()
        self.cli_json("approve", run_id)
        cfg = self.repo / ".ai" / "patchbay.toml"
        cfg.write_text(
            """[workflow]
worktree_root = ".ai/preexisting"
default_branch_prefix = "patchbay"
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

    def test_plan_failure_still_rejects_planner_workspace_mutation(self) -> None:
        (self.repo / ".ai").mkdir(parents=True, exist_ok=True)
        (self.repo / ".ai" / "patchbay.toml").write_text(
            """[phases.plan]
provider = "gemini_cli"

[commands_allowlist]
test = []
""",
            encoding="utf-8",
        )

        def mutating_planner(**kwargs: object) -> str:
            cwd = Path(kwargs["cwd"])
            (cwd / "planner-side-effect.txt").write_text("bad\n", encoding="utf-8")
            return "not a valid plan"

        with mock.patch.dict(service.PLANNERS, {"gemini_cli": mutating_planner}):
            with self.assertRaises(SafetyError):
                service.plan(self.repo, task="planner mutates then fails")

    def test_review_failure_still_rejects_reviewer_worktree_mutation(self) -> None:
        run_id = self.create_planned_run()
        self.cli_json("approve", run_id)
        self.cli_json("write", run_id, "--mock")
        self.cli_json("test", run_id)
        run_path = self.repo / ".ai" / "runs" / run_id
        status = json.loads((run_path / "STATUS.json").read_text(encoding="utf-8"))
        worktree = Path(status["worktree_path"])

        def mutating_reviewer(**kwargs: object) -> str:
            (worktree / "review-side-effect.txt").write_text("bad\n", encoding="utf-8")
            raise AiFlowError("reviewer failed after mutating", stage="review")

        with mock.patch.dict(service.REVIEWERS, {"codex_cli": mutating_reviewer}):
            with self.assertRaises(SafetyError):
                service.review(self.repo, run_id)

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
        self.allow_apply_without_tests()
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

    def test_apply_rejects_executor_provider_config(self) -> None:
        self.allow_apply_without_tests()
        run_id = self.create_planned_run()
        self.cli_json("approve", run_id)
        self.cli_json("write", run_id, "--mock")
        self.cli_json("test", run_id)
        self.cli_json("review", run_id, "--mock")
        (self.repo / ".ai" / "patchbay.toml").write_text(
            """[phases.apply]
provider = "codex_cli"

[workflow]
allow_apply_without_tests = true

[commands_allowlist]
test = []
""",
            encoding="utf-8",
        )

        result = self.cli("apply", run_id)

        self.assertNotEqual(result.returncode, 0)
        status = self.cli_json("status", run_id)
        self.assertEqual(status["status"], "FAILED")
        self.assertEqual(status["stage"], "apply")
        self.assertIn("does not support model/tool executors", status["error"])

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

    def test_review_tested_state_ignores_stale_verdict_file(self) -> None:
        (self.repo / ".ai").mkdir(parents=True, exist_ok=True)
        (self.repo / ".ai" / "patchbay.toml").write_text(
            """[phases.review]
provider = "mock"

[commands_allowlist]
test = []
""",
            encoding="utf-8",
        )
        run_id = self.create_planned_run()
        self.cli_json("approve", run_id)
        self.cli_json("write", run_id, "--mock")
        self.cli_json("test", run_id)
        run_path = self.repo / ".ai" / "runs" / run_id
        (run_path / "codex-reviewer.output.md").write_text(
            "CHANGES_REQUESTED\n\nBlocking Issues:\n1. stale cached result.\n",
            encoding="utf-8",
        )

        reviewed = self.cli_json("review", run_id)

        self.assertEqual(reviewed["status"], "REVIEWED_PASS")
        self.assertIn("Mock review passed", (run_path / "REVIEW.md").read_text(encoding="utf-8"))


class PhaseResolverTests(unittest.TestCase):
    """Tests for resolve_phase and per-phase config overlay."""

    def setUp(self) -> None:
        import copy
        from scripts.ai_flow.config import DEFAULT_CONFIG
        self.default_cfg = copy.deepcopy(DEFAULT_CONFIG)

    def test_legacy_config_resolves_plan_to_claude_cli(self) -> None:
        """Without [phases], plan provider should resolve to claude_cli from legacy defaults."""
        cfg = dict(self.default_cfg)
        cfg.pop("phases", None)
        phase = resolve_phase(cfg, "plan")
        self.assertEqual(phase["provider"], "claude_cli")
        self.assertEqual(phase["model"], "claude-opus-4-7")
        self.assertEqual(phase["command_key"], "claude")

    def test_legacy_config_resolves_review_to_codex_cli(self) -> None:
        cfg = dict(self.default_cfg)
        cfg.pop("phases", None)
        phase = resolve_phase(cfg, "review")
        self.assertEqual(phase["provider"], "codex_cli")
        self.assertEqual(phase["model"], "gpt-5.5")
        self.assertEqual(phase["command_key"], "codex")

    def test_legacy_config_resolves_write_from_writer_provider(self) -> None:
        cfg = dict(self.default_cfg)
        cfg.pop("phases", None)
        cfg.setdefault("writer", {})["provider"] = "reasonix_cli"
        phase = resolve_phase(cfg, "write")
        self.assertEqual(phase["provider"], "reasonix_cli")

    def test_legacy_writer_provider_falls_back_to_reasonix_cli(self) -> None:
        cfg = dict(self.default_cfg)
        cfg.pop("phases", None)
        cfg.pop("writer", None)
        phase = resolve_phase(cfg, "write")
        self.assertEqual(phase["provider"], "reasonix_cli")

    def test_phases_plan_override_provider(self) -> None:
        cfg = dict(self.default_cfg)
        cfg.setdefault("phases", {})["plan"] = {"provider": "codex_cli", "model": "gpt-5.5"}
        phase = resolve_phase(cfg, "plan")
        self.assertEqual(phase["provider"], "codex_cli")
        self.assertEqual(phase["model"], "gpt-5.5")

    def test_plan_provider_override_defaults_command_key_to_provider(self) -> None:
        cfg = dict(self.default_cfg)
        cfg.setdefault("phases", {})["plan"] = {"provider": "gemini_cli"}
        phase = resolve_phase(cfg, "plan")
        self.assertEqual(phase["command_key"], "gemini")
        self.assertEqual(phase["model"], "gemini-2.5-pro")

    def test_review_provider_override_defaults_command_key_to_provider(self) -> None:
        cfg = dict(self.default_cfg)
        cfg.setdefault("phases", {})["review"] = {"provider": "claude_cli"}
        phase = resolve_phase(cfg, "review")
        self.assertEqual(phase["command_key"], "claude")
        self.assertEqual(phase["model"], "claude-opus-4-7")

    def test_codex_provider_override_defaults_model_to_codex(self) -> None:
        cfg = dict(self.default_cfg)
        cfg.setdefault("phases", {})["plan"] = {"provider": "codex_cli"}
        phase = resolve_phase(cfg, "plan")
        self.assertEqual(phase["command_key"], "codex")
        self.assertEqual(phase["model"], "gpt-5.5")

    def test_phase_model_override_does_not_mutate_config_models(self) -> None:
        from scripts.ai_flow.service import _phase_config

        cfg = dict(self.default_cfg)
        cfg.setdefault("phases", {})["plan"] = {
            "provider": "codex_cli",
            "model": "codex-plan-model",
        }
        phase = resolve_phase(cfg, "plan")
        scoped = _phase_config(cfg, role="planner", model=phase["model"])
        self.assertEqual(scoped["models"]["planner"], "codex-plan-model")
        self.assertEqual(cfg["models"]["planner"], "claude-opus-4-7")

    def test_phase_command_creates_command_key_alias(self) -> None:
        cfg = dict(self.default_cfg)
        cfg.setdefault("phases", {})["plan"] = {
            "provider": "codex_cli",
            "command": "custom-codex --flag",
        }
        phase = resolve_phase(cfg, "plan")
        self.assertEqual(phase["command_key"], "phase_plan")
        self.assertEqual(cfg["commands"]["phase_plan"], "custom-codex --flag")

    def test_phases_write_override_uses_command_key(self) -> None:
        cfg = dict(self.default_cfg)
        cfg.setdefault("phases", {})["write"] = {"provider": "reasonix_cli", "command_key": "myreasonix"}
        phase = resolve_phase(cfg, "write")
        self.assertEqual(phase["command_key"], "myreasonix")

    def test_fix_phase_defaults_to_write_provider(self) -> None:
        cfg = dict(self.default_cfg)
        cfg.setdefault("phases", {})["write"] = {"provider": "reasonix_cli"}
        phase = resolve_phase(cfg, "fix")
        self.assertEqual(phase["provider"], "reasonix_cli")

    def test_fix_phase_defaults_to_write_model(self) -> None:
        cfg = dict(self.default_cfg)
        cfg.setdefault("phases", {})["write"] = {
            "provider": "reasonix_cli",
            "model": "writer-phase-model",
        }
        phase = resolve_phase(cfg, "fix")
        self.assertEqual(phase["model"], "writer-phase-model")

    def test_fix_phase_defaults_to_write_command_key(self) -> None:
        cfg = dict(self.default_cfg)
        cfg.setdefault("phases", {})["write"] = {
            "provider": "reasonix_cli",
            "command_key": "custom_reasonix",
        }
        phase = resolve_phase(cfg, "fix")
        self.assertEqual(phase["command_key"], "custom_reasonix")

    def test_fix_phase_defaults_to_write_command(self) -> None:
        cfg = dict(self.default_cfg)
        cfg.setdefault("phases", {})["write"] = {
            "provider": "reasonix_cli",
            "command": "custom-reasonix --flag",
        }
        phase = resolve_phase(cfg, "fix")
        self.assertEqual(phase["command_key"], "phase_write")
        self.assertEqual(cfg["commands"]["phase_write"], "custom-reasonix --flag")

    def test_fix_phase_defaults_to_fully_resolved_write_phase(self) -> None:
        cfg = dict(self.default_cfg)
        cfg["models"] = dict(self.default_cfg["models"])
        cfg["models"]["writer"] = "custom-writer-model"
        cfg.setdefault("phases", {})["write"] = {
            "env": {"PATCHBAY_WRITE_ONLY": "yes"},
            "timeout": 123,
        }
        write_phase = resolve_phase(cfg, "write")
        phase = resolve_phase(cfg, "fix")
        self.assertEqual(write_phase["provider"], "reasonix_cli")
        self.assertEqual(write_phase["model"], "custom-writer-model")
        self.assertEqual(phase["provider"], write_phase["provider"])
        self.assertEqual(phase["model"], write_phase["model"])
        self.assertEqual(phase["command_key"], write_phase["command_key"])
        self.assertEqual(phase["timeout"], 123)
        self.assertEqual(phase["env"]["PATCHBAY_WRITE_ONLY"], "yes")

    def test_fix_phase_explicit_override(self) -> None:
        cfg = dict(self.default_cfg)
        cfg.setdefault("phases", {})["write"] = {"provider": "reasonix_cli"}
        cfg.setdefault("phases", {})["fix"] = {"provider": "mock"}
        phase = resolve_phase(cfg, "fix")
        self.assertEqual(phase["provider"], "mock")

    def test_default_config_resolves_write_to_reasonix_cli(self) -> None:
        """With no overrides, DEFAULT_CONFIG write provider is reasonix_cli."""
        cfg = dict(self.default_cfg)
        phase = resolve_phase(cfg, "write")
        self.assertEqual(phase["provider"], "reasonix_cli")
        self.assertEqual(phase["command_key"], "reasonix")
        self.assertEqual(phase["model"], "deepseek-v4-pro")

    def test_example_toml_defaults_writer_to_reasonix_cli(self) -> None:
        """EXAMPLE_TOML should default to reasonix_cli and not advertise deepseek_api."""
        from scripts.ai_flow.service import EXAMPLE_TOML
        self.assertIn('provider = "reasonix_cli"', EXAMPLE_TOML)
        self.assertNotIn("deepseek_api", EXAMPLE_TOML)

    def test_test_phase_has_no_provider_by_default(self) -> None:
        cfg = dict(self.default_cfg)
        cfg.pop("phases", None)
        phase = resolve_phase(cfg, "test")
        self.assertEqual(phase["provider"], "")

    def test_apply_phase_has_no_provider_by_default(self) -> None:
        cfg = dict(self.default_cfg)
        cfg.pop("phases", None)
        phase = resolve_phase(cfg, "apply")
        self.assertEqual(phase["provider"], "")

    def test_resolved_phase_always_has_env_dict(self) -> None:
        cfg = dict(self.default_cfg)
        cfg.pop("phases", None)
        for p in ("plan", "write", "review", "fix", "test", "apply"):
            phase = resolve_phase(cfg, p)
            self.assertIsInstance(phase.get("env"), dict, f"{p} env not a dict")

    def test_phase_env_merges_with_parent_environment(self) -> None:
        cfg = dict(self.default_cfg)
        cfg.setdefault("phases", {})["plan"] = {"env": {"PATCHBAY_TEST_ENV": "configured"}}
        phase = resolve_phase(cfg, "plan")
        self.assertEqual(phase["env"]["PATCHBAY_TEST_ENV"], "configured")
        self.assertIn("PATH", {key.upper(): value for key, value in phase["env"].items()})

    def test_resolved_phase_always_has_timeout(self) -> None:
        cfg = dict(self.default_cfg)
        cfg.pop("phases", None)
        for p in ("plan", "write", "review", "fix", "test", "apply"):
            phase = resolve_phase(cfg, p)
            self.assertIn("timeout", phase)
            self.assertGreaterEqual(phase["timeout"], 0)


class ProviderRegistryTests(unittest.TestCase):
    """Tests for the adapter provider registries."""

    def test_planners_registry_has_all_providers(self) -> None:
        from scripts.ai_flow.adapters import PLANNERS
        for provider in ("claude_cli", "codex_cli", "gemini_cli", "mock"):
            self.assertIn(provider, PLANNERS, f"{provider} missing from PLANNERS")
            self.assertTrue(callable(PLANNERS[provider]), f"{provider} not callable")

    def test_writers_registry_has_reasonix_cli_and_mock(self) -> None:
        from scripts.ai_flow.adapters import WRITERS
        self.assertEqual(set(WRITERS.keys()), {"reasonix_cli", "mock"})
        self.assertNotIn("deepseek_api", WRITERS)
        self.assertTrue(callable(WRITERS["reasonix_cli"]))
        self.assertTrue(callable(WRITERS["mock"]))

    def test_reviewers_registry_has_all_providers(self) -> None:
        from scripts.ai_flow.adapters import REVIEWERS
        for provider in ("claude_cli", "codex_cli", "gemini_cli", "mock"):
            self.assertIn(provider, REVIEWERS, f"{provider} missing from REVIEWERS")
            self.assertTrue(callable(REVIEWERS[provider]), f"{provider} not callable")

    def test_fixers_registry_mirrors_writers(self) -> None:
        from scripts.ai_flow.adapters import FIXERS, WRITERS
        self.assertNotIn("deepseek_api", FIXERS)
        for key in WRITERS:
            self.assertIn(key, FIXERS)
            self.assertIs(FIXERS[key], WRITERS[key])

    def test_planner_providers_accept_command_key_timeout_env(self) -> None:
        """All non-mock planner providers accept command_key, timeout, env kwargs."""
        from scripts.ai_flow.adapters import PLANNERS
        import inspect
        for name in ("claude_cli", "codex_cli", "gemini_cli"):
            sig = inspect.signature(PLANNERS[name])
            params = sig.parameters
            self.assertIn("command_key", params, f"{name} missing command_key param")
            self.assertIn("timeout", params, f"{name} missing timeout param")
            self.assertIn("env", params, f"{name} missing env param")

    def test_reviewer_providers_accept_command_key_timeout_env(self) -> None:
        """All non-mock reviewer providers accept command_key, timeout, env kwargs."""
        from scripts.ai_flow.adapters import REVIEWERS
        import inspect
        for name in ("claude_cli", "codex_cli", "gemini_cli"):
            sig = inspect.signature(REVIEWERS[name])
            params = sig.parameters
            self.assertIn("command_key", params, f"{name} missing command_key param")
            self.assertIn("timeout", params, f"{name} missing timeout param")
            self.assertIn("env", params, f"{name} missing env param")


class McpSchemaTests(unittest.TestCase):
    """Tests for MCP server tool descriptions (host-agnostic)."""

    def test_tool_list_includes_updated_descriptions(self) -> None:
        from scripts.ai_flow.mcp_server import handle
        tools_response = handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        tools = {tool["name"]: tool["description"] for tool in tools_response["result"]["tools"]}

        # Canonical tools should have non-trivial descriptions
        self.assertIn("patchbay_plan", tools)
        self.assertIn("phases.plan", tools["patchbay_plan"].lower())
        self.assertIn("patchbay_write", tools)
        self.assertIn("provider", tools["patchbay_write"].lower())
        self.assertIn("patchbay_review", tools)
        self.assertIn("phases.review", tools["patchbay_review"].lower())
        self.assertIn("patchbay_metrics", tools)
        self.assertIn("run_metrics", tools["patchbay_metrics"])
        self.assertIn("patchbay_doctor", tools)
        self.assertIn("read-only readiness", tools["patchbay_doctor"].lower())
        self.assertIn("patchbay_setup", tools)
        self.assertIn("initialize patchbay", tools["patchbay_setup"].lower())

        # Legacy aliases should still exist and mention alias status
        self.assertIn("ai_flow_plan", tools)
        self.assertIn("legacy", tools["ai_flow_plan"].lower())

    def test_canonical_and_legacy_names_both_present(self) -> None:
        from scripts.ai_flow.mcp_server import handle
        tools_response = handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        names = {tool["name"] for tool in tools_response["result"]["tools"]}
        for canonical in ("patchbay_plan", "patchbay_approve", "patchbay_write", "patchbay_test",
                          "patchbay_review", "patchbay_fix", "patchbay_status", "patchbay_context",
                          "patchbay_metrics", "patchbay_doctor", "patchbay_setup", "patchbay_trace", "patchbay_diff", "patchbay_apply", "patchbay_agent"):
            self.assertIn(canonical, names, f"{canonical} missing from tools/list")
        for legacy in ("ai_flow_plan", "ai_flow_approve", "ai_flow_write", "ai_flow_test",
                       "ai_flow_review", "ai_flow_fix", "ai_flow_status", "ai_flow_context",
                       "ai_flow_metrics", "ai_flow_doctor", "ai_flow_setup", "ai_flow_trace", "ai_flow_diff", "ai_flow_apply", "ai_flow_agent"):
            self.assertIn(legacy, names, f"{legacy} missing from tools/list")


class MockProviderSmokeTests(AiFlowTestCase):
    """End-to-end smoke tests using mock providers selected via phase config."""

    def setUp(self) -> None:
        super().setUp()
        (self.repo / ".ai").mkdir(parents=True, exist_ok=True)

    def test_non_default_planner_via_phases_config(self) -> None:
        """A plan with phases.plan.provider='mock' (no --mock flag) uses mock via registry."""
        cfg_path = self.repo / ".ai" / "patchbay.toml"
        cfg_path.write_text(
            """[phases.plan]
provider = "mock"
model = "mock-model"

[commands_allowlist]
test = []
""",
            encoding="utf-8",
        )
        result = self.cli_json("plan", "--task", "phases-config-plan")
        self.assertIn("run_id", result)
        run_path = self.repo / ".ai" / "runs" / result["run_id"]
        self.assertTrue((run_path / "PLAN.md").exists())
        self.assertTrue((run_path / "plan.json").exists())

    def test_writer_provider_via_phases_config(self) -> None:
        """write phase with phases.write.provider='mock' should produce mock output."""
        cfg_path = self.repo / ".ai" / "patchbay.toml"
        cfg_path.write_text(
            """[phases.write]
provider = "mock"

[commands_allowlist]
test = []
""",
            encoding="utf-8",
        )
        planned = self.cli_json("plan", "--task", "mock phases writer", "--mock")
        run_id = planned["run_id"]
        self.cli_json("approve", run_id)
        self.cli_json("write", run_id)
        self.cli_json("test", run_id)
        status = self.cli_json("status", run_id)
        self.assertEqual(status["status"], "TESTED")

    def test_test_commands_via_phases_config(self) -> None:
        cfg_path = self.repo / ".ai" / "patchbay.toml"
        cfg_path.write_text(
            """[phases.test]
commands = ['python -c "print(12345)"']
timeout = 30

[commands_allowlist]
test = ['python -c "print(12345)"']
""",
            encoding="utf-8",
        )
        planned = self.cli_json("plan", "--task", "mock phases test", "--mock")
        run_id = planned["run_id"]
        self.cli_json("approve", run_id)
        self.cli_json("write", run_id, "--mock")
        self.cli_json("test", run_id)
        run_path = self.repo / ".ai" / "runs" / run_id
        self.assertIn("12345", (run_path / "TEST.log").read_text(encoding="utf-8"))

    def test_test_env_via_phases_config(self) -> None:
        cfg_path = self.repo / ".ai" / "patchbay.toml"
        cfg_path.write_text(
            r"""[phases.test]
commands = ["python -c \"import os; print(os.environ.get('PATCHBAY_PHASE_ENV', 'missing'))\""]
env = { PATCHBAY_PHASE_ENV = "phase-env-value" }

[commands_allowlist]
test = ["python -c \"import os; print(os.environ.get('PATCHBAY_PHASE_ENV', 'missing'))\""]
""",
            encoding="utf-8",
        )
        planned = self.cli_json("plan", "--task", "mock phases test env", "--mock")
        run_id = planned["run_id"]
        self.cli_json("approve", run_id)
        self.cli_json("write", run_id, "--mock")
        self.cli_json("test", run_id)
        run_path = self.repo / ".ai" / "runs" / run_id
        self.assertIn("phase-env-value", (run_path / "TEST.log").read_text(encoding="utf-8"))

    def test_reviewer_provider_via_phases_config(self) -> None:
        """review phase with phases.review.provider='mock' should pass."""
        cfg_path = self.repo / ".ai" / "patchbay.toml"
        cfg_path.write_text(
            """[phases.review]
provider = "mock"

[commands_allowlist]
test = []
""",
            encoding="utf-8",
        )
        planned = self.cli_json("plan", "--task", "mock phases review", "--mock")
        run_id = planned["run_id"]
        self.cli_json("approve", run_id)
        self.cli_json("write", run_id, "--mock")
        self.cli_json("test", run_id)
        self.cli_json("review", run_id, "--mock")
        status = self.cli_json("status", run_id)
        self.assertEqual(status["status"], "REVIEWED_PASS")


if __name__ == "__main__":
    unittest.main()
