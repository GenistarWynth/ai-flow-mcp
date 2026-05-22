from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from .errors import AiFlowError


PLAN_JSON_BEGIN = "BEGIN_AI_FLOW_PLAN_JSON"
PLAN_JSON_END = "END_AI_FLOW_PLAN_JSON"
WRITER_SUMMARY_BEGIN = "BEGIN_WRITER_SUMMARY"
WRITER_SUMMARY_END = "END_WRITER_SUMMARY"
DIFF_BEGIN = "BEGIN_DIFF"
DIFF_END = "END_DIFF"
NEED_FILES_BEGIN = "BEGIN_NEED_FILES"
NEED_FILES_END = "END_NEED_FILES"


@dataclass
class PlannerOutput:
    plan_json: dict[str, Any]
    markdown: str
    raw: str


@dataclass
class WriterOutput:
    summary: str
    diff: str | None
    needed_files: list[str]
    raw: str


def _extract_between(text: str, begin: str, end: str) -> str | None:
    pattern = re.compile(
        r"(?m)^" + re.escape(begin) + r"\s*$\s*(.*?)\s*^" + re.escape(end) + r"\s*$",
        flags=re.DOTALL | re.MULTILINE,
    )
    match = pattern.search(text)
    if not match:
        return None
    return match.group(1).strip()


def _remove_block(text: str, begin: str, end: str) -> str:
    pattern = re.compile(
        re.escape(begin) + r"\s*.*?\s*" + re.escape(end),
        flags=re.DOTALL,
    )
    return pattern.sub("", text).strip()


def parse_planner_output(text: str) -> PlannerOutput:
    raw_json = _extract_between(text, PLAN_JSON_BEGIN, PLAN_JSON_END)
    if raw_json is None:
        raise AiFlowError(
            "Planner output did not contain BEGIN_AI_FLOW_PLAN_JSON / END_AI_FLOW_PLAN_JSON.",
            stage="plan",
            suggested_next_action="Rerun plan with --mock or fix the planner prompt/CLI configuration.",
        )
    try:
        plan_json = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise AiFlowError(
            f"Planner JSON could not be parsed: {exc}",
            stage="plan",
            suggested_next_action="Ask the planner to emit valid JSON inside the sentinel block.",
        ) from exc
    markdown = _remove_block(text, PLAN_JSON_BEGIN, PLAN_JSON_END).strip()
    if not markdown:
        markdown = "# Implementation Plan\n\nPlanner returned machine-readable JSON only.\n"
    return PlannerOutput(plan_json=plan_json, markdown=markdown + "\n", raw=text)


def parse_writer_output(text: str) -> WriterOutput:
    summary = _extract_between(text, WRITER_SUMMARY_BEGIN, WRITER_SUMMARY_END)
    diff = _extract_between(text, DIFF_BEGIN, DIFF_END)
    needed_raw = _extract_between(text, NEED_FILES_BEGIN, NEED_FILES_END)
    needed_files: list[str] = []
    if needed_raw:
        try:
            parsed = json.loads(needed_raw)
        except json.JSONDecodeError as exc:
            raise AiFlowError(
                f"Writer NEED_FILES block is not valid JSON: {exc}",
                stage="write",
            ) from exc
        if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
            raise AiFlowError("Writer NEED_FILES block must be a JSON string array.", stage="write")
        needed_files = parsed
    if summary is None:
        summary = _remove_block(text, DIFF_BEGIN, DIFF_END).strip()
    return WriterOutput(summary=(summary or "").strip(), diff=diff, needed_files=needed_files, raw=text)


def review_verdict(text: str) -> str:
    stripped = text.lstrip()
    if stripped.startswith("PASS"):
        return "PASS"
    if stripped.startswith("CHANGES_REQUESTED"):
        return "CHANGES_REQUESTED"
    raise AiFlowError(
        "Reviewer output must start with PASS or CHANGES_REQUESTED.",
        stage="review",
        suggested_next_action="Rerun review with --mock or adjust the reviewer prompt/CLI configuration.",
    )
