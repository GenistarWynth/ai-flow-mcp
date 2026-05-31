from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Callable

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from ai_flow.agent import agent_message
    from ai_flow import service
    from ai_flow.config_wizard import run_config_wizard
    from ai_flow.doctor import run_doctor
    from ai_flow.setup_flow import run_setup
    from ai_flow.skill_install import run_skill_doctor, run_skill_install, run_skill_print
else:
    from .agent import agent_message
    from . import service
    from .config_wizard import run_config_wizard
    from .doctor import run_doctor
    from .setup_flow import run_setup
    from .skill_install import run_skill_doctor, run_skill_install, run_skill_print


ROOT = Path(os.environ.get("PATCHBAY_ROOT") or Path.cwd())
SERVER_NAME = "patchbay"
SERVER_VERSION = "0.1.0"


def patchbay_plan(task: str, background: bool = False) -> dict[str, Any]:
    if background:
        return service.start_background_phase(ROOT, "plan", task=task)
    return service.plan(ROOT, task=task)


def patchbay_approve(run_id: str) -> dict[str, Any]:
    return service.approve(ROOT, run_id)


def patchbay_write(run_id: str, background: bool = False) -> dict[str, Any]:
    if background:
        return service.start_background_phase(ROOT, "write", run_id=run_id)
    return service.write(ROOT, run_id)


def patchbay_test(run_id: str, background: bool = False) -> dict[str, Any]:
    if background:
        return service.start_background_phase(ROOT, "test", run_id=run_id)
    return service.test(ROOT, run_id)


def patchbay_review(run_id: str, background: bool = False) -> dict[str, Any]:
    if background:
        return service.start_background_phase(ROOT, "review", run_id=run_id)
    return service.review(ROOT, run_id)


def patchbay_fix(run_id: str, background: bool = False) -> dict[str, Any]:
    if background:
        return service.start_background_phase(ROOT, "fix", run_id=run_id)
    return service.fix(ROOT, run_id)


def patchbay_status(run_id: str) -> dict[str, Any]:
    return service.status(ROOT, run_id)


def patchbay_context(
    run_id: str,
    since_event: int = 0,
    since_trace: int = 0,
    include_trace: bool = False,
) -> dict[str, Any]:
    return service.context(
        ROOT,
        run_id,
        since_event=since_event,
        since_trace=since_trace,
        include_trace=include_trace,
    )


def patchbay_metrics(run_id: str) -> dict[str, Any]:
    return service.metrics(ROOT, run_id)


def patchbay_doctor(include_mcp: bool = False, skill_path: str = "", host: str = "codex") -> dict[str, Any]:
    return run_doctor(ROOT, include_mcp=include_mcp, skill_path=skill_path or None, host=host)


def patchbay_setup(
    host: str = "codex",
    skill_path: str = "",
    dry_run: bool = False,
    skip_skill: bool = False,
    skip_mcp: bool = False,
    mcp_dry_run: bool = False,
    probe_mcp: bool = False,
    create_config: bool = True,
) -> dict[str, Any]:
    return run_setup(
        ROOT,
        host=host,
        skill_path=skill_path or None,
        dry_run=dry_run,
        skip_skill=skip_skill,
        skip_mcp=skip_mcp,
        mcp_dry_run=mcp_dry_run,
        probe_mcp=probe_mcp,
        create_config=create_config,
    )


def patchbay_skill_install(host: str = "codex", skill_path: str = "", dry_run: bool = False) -> dict[str, Any]:
    return run_skill_install(ROOT, host=host, path=skill_path or None, dry_run=dry_run)


def patchbay_skill_print(host: str = "codex") -> dict[str, Any]:
    return run_skill_print(ROOT, host=host)


def patchbay_skill_doctor(host: str = "codex", skill_path: str = "") -> dict[str, Any]:
    return run_skill_doctor(ROOT, host=host, path=skill_path or None)


def patchbay_events(run_id: str, since: int = 0, phase: str = "") -> dict[str, Any]:
    return service.events(ROOT, run_id, since=since, phase=phase or None)


def patchbay_trace(run_id: str, since: int = 0, phase: str = "") -> dict[str, Any]:
    return service.trace(ROOT, run_id, since=since, phase=phase or None)


def patchbay_runs(limit: int = 20) -> dict[str, Any]:
    return service.runs(ROOT, limit=limit)


def patchbay_artifact(run_id: str, artifact: str, tail: int | None = None) -> dict[str, Any]:
    return service.artifact(ROOT, run_id, artifact, tail=tail)


def patchbay_config_show() -> dict[str, Any]:
    return run_config_wizard(ROOT, show=True)


def patchbay_config_phase_set(
    phase: str,
    provider: str,
    model: str = "",
    command_key: str = "",
) -> dict[str, Any]:
    return run_config_wizard(ROOT, phase=phase, provider=provider, model=model, command_key=command_key)


def patchbay_config_command_set(key: str, command: str) -> dict[str, Any]:
    return run_config_wizard(ROOT, command_key_name=key, command_value=command)


def patchbay_config_test_add(command: str) -> dict[str, Any]:
    return run_config_wizard(ROOT, test_command=command)


def patchbay_config_profile_apply(profile: str = "economy") -> dict[str, Any]:
    return run_config_wizard(ROOT, profile=profile or "economy")


def patchbay_config_profile_show() -> dict[str, Any]:
    return run_config_wizard(ROOT, show_profile=True)


def patchbay_config_provider_add_cli(
    provider_id: str,
    roles: list[str],
    command: str,
    args: list[str] | None = None,
    prompt_mode: str = "stdin",
    output_contract: str = "writer_diff",
    activate_economy: bool = False,
    economy_model: str = "",
    economy_label: str = "",
) -> dict[str, Any]:
    return run_config_wizard(
        ROOT,
        provider_id=provider_id,
        provider_roles=roles,
        provider_command=command,
        provider_args=args or [],
        prompt_mode=prompt_mode,
        output_contract=output_contract,
        activate_economy=activate_economy,
        economy_model=economy_model,
        economy_label=economy_label,
    )


def patchbay_diff(run_id: str) -> dict[str, str]:
    return {"diff": service.diff(ROOT, run_id)}


def patchbay_apply(run_id: str) -> dict[str, Any]:
    return service.apply(ROOT, run_id)


def patchbay_agent(
    message: str,
    run_id: str = "",
    confirmation: str = "none",
    include: dict[str, Any] | None = None,
    max_fix_rounds: int | None = None,
    background: bool = False,
) -> dict[str, Any]:
    return agent_message(
        ROOT,
        message,
        run_id=run_id or None,
        confirmation=confirmation or "none",
        include=include or {},
        max_fix_rounds=max_fix_rounds,
        background=background,
    )


CANONICAL_TOOLS: dict[str, Callable[..., Any]] = {
    "patchbay_agent": patchbay_agent,
    "patchbay_plan": patchbay_plan,
    "patchbay_approve": patchbay_approve,
    "patchbay_write": patchbay_write,
    "patchbay_test": patchbay_test,
    "patchbay_review": patchbay_review,
    "patchbay_fix": patchbay_fix,
    "patchbay_status": patchbay_status,
    "patchbay_context": patchbay_context,
    "patchbay_metrics": patchbay_metrics,
    "patchbay_doctor": patchbay_doctor,
    "patchbay_setup": patchbay_setup,
    "patchbay_install": patchbay_setup,
    "patchbay_skill_install": patchbay_skill_install,
    "patchbay_skill_print": patchbay_skill_print,
    "patchbay_skill_doctor": patchbay_skill_doctor,
    "patchbay_events": patchbay_events,
    "patchbay_trace": patchbay_trace,
    "patchbay_runs": patchbay_runs,
    "patchbay_artifact": patchbay_artifact,
    "patchbay_config_show": patchbay_config_show,
    "patchbay_config_phase_set": patchbay_config_phase_set,
    "patchbay_config_command_set": patchbay_config_command_set,
    "patchbay_config_test_add": patchbay_config_test_add,
    "patchbay_config_profile_apply": patchbay_config_profile_apply,
    "patchbay_config_profile_show": patchbay_config_profile_show,
    "patchbay_config_provider_add_cli": patchbay_config_provider_add_cli,
    "patchbay_diff": patchbay_diff,
    "patchbay_apply": patchbay_apply,
}

LEGACY_TOOLS: dict[str, Callable[..., Any]] = {
    "ai_flow_agent": patchbay_agent,
    "ai_flow_plan": patchbay_plan,
    "ai_flow_approve": patchbay_approve,
    "ai_flow_write": patchbay_write,
    "ai_flow_test": patchbay_test,
    "ai_flow_review": patchbay_review,
    "ai_flow_fix": patchbay_fix,
    "ai_flow_status": patchbay_status,
    "ai_flow_context": patchbay_context,
    "ai_flow_metrics": patchbay_metrics,
    "ai_flow_doctor": patchbay_doctor,
    "ai_flow_setup": patchbay_setup,
    "ai_flow_install": patchbay_setup,
    "ai_flow_skill_install": patchbay_skill_install,
    "ai_flow_skill_print": patchbay_skill_print,
    "ai_flow_skill_doctor": patchbay_skill_doctor,
    "ai_flow_events": patchbay_events,
    "ai_flow_trace": patchbay_trace,
    "ai_flow_runs": patchbay_runs,
    "ai_flow_artifact": patchbay_artifact,
    "ai_flow_config_show": patchbay_config_show,
    "ai_flow_config_phase_set": patchbay_config_phase_set,
    "ai_flow_config_command_set": patchbay_config_command_set,
    "ai_flow_config_test_add": patchbay_config_test_add,
    "ai_flow_config_profile_apply": patchbay_config_profile_apply,
    "ai_flow_config_profile_show": patchbay_config_profile_show,
    "ai_flow_config_provider_add_cli": patchbay_config_provider_add_cli,
    "ai_flow_diff": patchbay_diff,
    "ai_flow_apply": patchbay_apply,
}

TOOLS: dict[str, Callable[..., Any]] = {**CANONICAL_TOOLS, **LEGACY_TOOLS}


def _tool_schema(name: str) -> dict[str, Any]:
    if name.endswith("_agent"):
        properties: dict[str, Any] = {
            "message": {
                "type": "string",
                "description": "Natural-language task or instruction for the conversational Patchbay Agent. Explicit setup/help/status/readiness/routing/gate-status prompts are handled locally without starting a model run; help prompts include `help`, `Patchbay 怎么用`, and `使用说明`; readiness prompts include `readiness`, `readiness for Claude Desktop`, `patchbay doctor`, `检查环境`, `环境自检`, and `检查 Gemini 命令行环境`, and host-targeted readiness replies include `setup_host`/`doctor.host`; status/runs prompts include `status`, `查看最近运行`, and `任务列表`; next-step prompts include `what should I do next`, `next step`, `现在该干什么`, and `下一步是什么`, and return `action: next_step` plus safe handoff actions without advancing gates; gate-status prompts include `why can't I apply`, `what is blocking apply`, `门禁状态`, and `为什么不能应用`, and return `action: gate_status` plus `gate_diagnosis.next_action` without advancing gates; direct `apply` on a selected run also returns `gate_diagnosis.next_action` and safe diagnostic actions when apply is blocked, instead of requesting confirmation; routing questions such as `what model will write/fix use`, `is writer using cheap model`, or `现在写手是不是走便宜模型` return read-only `action: profile_show`, and include `metrics.efficiency_summary` when a run_id is supplied; setup prompts can name a host such as `patchbay setup for Claude Desktop`, `帮我配置 Patchbay 到 Claude 桌面`, `安装到 Claude 桌面`, `install patchbay for Gemini CLI`, `install Codex Skill`, `register MCP for Claude Desktop`, `安装 Codex Skill`, or `注册 MCP 到 Gemini 命令行`; `configure DeepSeek provider` returns a safe command action for `patchbay config provider add-cli ... --activate-economy`, while `configure DeepSeek provider to <command>` registers that CLI writer and activates it for write/fix; `configure economy provider command to <path>` or `patchbay config --set-key providers.<id>.command --set-value <path>` repairs the active custom economy provider command without starting a run; `apply economy profile`, `configure reasonix command`, `configure reasonix command to <path>`, `配置 Reasonix 命令`, and `把 Reasonix 命令设为 <path>` update local routing configuration; metrics/cost/token and view prompts such as `diff`, `logs`, `artifact`, or `查看失败原因` with a run_id inspect that run, and without a run_id inspect the latest run if one exists, returning requested_view plus safe diagnostic_tab actions; gate-changing prompts such as approve/continue/apply without run_id return local guidance instead.",
            },
            "run_id": {"type": "string", "description": "Existing run id to continue or inspect."},
            "confirmation": {
                "type": "string",
                "enum": ["none", "plan_approved", "apply_approved"],
                "description": "Explicit confirmation for plan/apply gates.",
            },
            "include": {"type": "object", "description": "Optional artifact/diff include flags."},
            "max_fix_rounds": {"type": "integer", "description": "Optional fix-loop cap for this agent turn."},
            "background": {
                "type": "boolean",
                "description": "Run long planning or implementation turns in the background and poll status/events.",
            },
        }
        required = ["message"]
    elif name.endswith("_plan"):
        properties: dict[str, Any] = {"task": {"type": "string"}}
        properties["background"] = {"type": "boolean", "description": "Start phase in the background and poll events."}
        required = ["task"]
    elif name.endswith("_context"):
        properties = {
            "run_id": {"type": "string"},
            "since_event": {"type": "integer", "description": "Return events after raw event index N (default 0)."},
            "since_trace": {"type": "integer", "description": "Return trace entries after raw trace index N (default 0)."},
            "include_trace": {"type": "boolean", "description": "Merge trace entries into the handoff timeline."},
        }
        required = ["run_id"]
    elif name.endswith("_metrics"):
        properties = {"run_id": {"type": "string"}}
        required = ["run_id"]
    elif name.endswith("_skill_install"):
        properties = {
            "host": {"type": "string", "description": "Skill host: codex."},
            "skill_path": {"type": "string", "description": "Optional Codex skills root to install into."},
            "dry_run": {"type": "boolean", "description": "Preview Skill installation without copying files."},
        }
        required = []
    elif name.endswith("_skill_print"):
        properties = {"host": {"type": "string", "description": "Skill host: codex."}}
        required = []
    elif name.endswith("_skill_doctor"):
        properties = {
            "host": {"type": "string", "description": "Skill host: codex."},
            "skill_path": {
                "type": "string",
                "description": "Optional Codex skills root to inspect.",
            },
        }
        required = []
    elif name.endswith("_doctor"):
        properties = {
            "host": {
                "type": "string",
                "description": "MCP host or alias for concrete registration actions: codex, claude, claude-code, claude-desktop, gemini; also accepts names like Claude Desktop, Claude 桌面, Gemini CLI, or Gemini 命令行.",
            },
            "include_mcp": {
                "type": "boolean",
                "description": "Probe the stdio MCP server and verify required tools (default false; use only when tool-list evidence is needed).",
            },
            "skill_path": {
                "type": "string",
                "description": "Optional Codex skills root to inspect.",
            },
        }
        required = []
    elif name.endswith(("_setup", "_install")):
        properties = {
            "host": {
                "type": "string",
                "description": "MCP host or alias: codex, claude, claude-code, claude-desktop, gemini; also accepts names like Claude Desktop, Claude 桌面, Gemini CLI, or Gemini 命令行.",
            },
            "skill_path": {"type": "string", "description": "Optional Codex skills root to install into."},
            "dry_run": {"type": "boolean", "description": "Preview setup without writing files."},
            "skip_skill": {"type": "boolean", "description": "Skip Codex Skill installation."},
            "skip_mcp": {"type": "boolean", "description": "Skip MCP host registration helper."},
            "mcp_dry_run": {"type": "boolean", "description": "Preview MCP registration without writing host config."},
            "probe_mcp": {"type": "boolean", "description": "Run stdio MCP doctor after setup."},
            "create_config": {"type": "boolean", "description": "Create .ai/patchbay.toml from the example when missing."},
        }
        required = []
    elif name.endswith("_runs"):
        properties = {"limit": {"type": "integer"}}
        required = []
    elif name.endswith("_artifact"):
        properties = {
            "run_id": {"type": "string"},
            "artifact": {"type": "string"},
            "tail": {"type": "integer"},
        }
        required = ["run_id", "artifact"]
    elif name.endswith("_events") or name.endswith("_trace"):
        properties = {
            "run_id": {"type": "string"},
            "since": {"type": "integer", "description": "Return entries after raw line index N (default 0)."},
            "phase": {"type": "string", "description": "Optional filter by phase name."},
        }
        required = ["run_id"]
    elif name.endswith("_config_show"):
        properties = {}
        required = []
    elif name.endswith("_config_phase_set"):
        properties = {
            "phase": {"type": "string"},
            "provider": {"type": "string"},
            "model": {"type": "string"},
            "command_key": {"type": "string"},
        }
        required = ["phase", "provider"]
    elif name.endswith("_config_command_set"):
        properties = {"key": {"type": "string"}, "command": {"type": "string"}}
        required = ["key", "command"]
    elif name.endswith("_config_test_add"):
        properties = {"command": {"type": "string"}}
        required = ["command"]
    elif name.endswith("_config_profile_apply"):
        properties = {
            "profile": {
                "type": "string",
                "enum": ["economy"],
                "description": "Routing profile to apply. economy routes write/fix work to Reasonix/DeepSeek.",
            }
        }
        required = []
    elif name.endswith("_config_profile_show"):
        properties = {}
        required = []
    elif name.endswith("_config_provider_add_cli"):
        properties = {
            "provider_id": {"type": "string"},
            "roles": {"type": "array", "items": {"type": "string"}},
            "command": {"type": "string"},
            "args": {"type": "array", "items": {"type": "string"}},
            "prompt_mode": {"type": "string"},
            "output_contract": {"type": "string"},
            "activate_economy": {
                "type": "boolean",
                "description": "Also make this provider the economy write/fix route; requires write and fix roles.",
            },
            "economy_model": {"type": "string", "description": "Model label to record for the economy write/fix route."},
            "economy_label": {"type": "string", "description": "Human-readable label for this low-cost economy route."},
        }
        required = ["provider_id", "roles", "command", "output_contract"]
    else:
        properties = {"run_id": {"type": "string"}}
        if any(name.endswith(suffix) for suffix in ("_write", "_test", "_review", "_fix")):
            properties["background"] = {"type": "boolean", "description": "Start phase in the background and poll events."}
        required = ["run_id"]

    descriptions: dict[str, str] = {
        "patchbay_agent": "Primary conversational Patchbay Agent tool. Starts, resumes, advances, applies runs, and returns metrics/cost/token evidence while preserving plan/apply approval gates; explicit setup, help, status, readiness, readiness for Claude Desktop, what should I do next, 下一步是什么, why can't I apply, what is blocking apply, what model will write/fix use, is writer using cheap model, 门禁状态, 为什么不能应用, 现在写手是不是走便宜模型, patchbay doctor, Patchbay 怎么用, 查看最近运行, 任务列表, 检查环境, 环境自检, 检查 Gemini 命令行环境, economy profile, configure DeepSeek provider, configure DeepSeek provider to <command>, configure economy provider command to <path>, configure reasonix command, configure reasonix command to <path>, 配置 Reasonix 命令, and 把 Reasonix 命令设为 <path> prompts return local answers with structured actions[] for safe client follow-ups; configure DeepSeek provider returns a safe command action for patchbay_config_provider_add_cli / add-cli --activate-economy, while configure DeepSeek provider to <command> registers that CLI writer and activates write/fix economy routing; configure economy provider command to <path> or patchbay config --set-key providers.<id>.command --set-value <path> repairs the active custom economy provider command without starting a run; custom provider command gaps report providers.<id>.command and expose configure_economy_provider_command copyable command actions; metrics/cost/token and view prompts like diff/logs/artifact/查看失败原因 without run_id inspect the latest run when available and return requested_view plus safe diagnostic_tab actions for the matching diagnostic tab; next-step prompts return action next_step without advancing gates, gate-status prompts return action gate_status with gate_diagnosis.next_action without advancing gates, blocked direct apply also returns gate_diagnosis.next_action plus safe diagnostic actions, routing questions return read-only action profile_show and include metrics.efficiency_summary when a run_id is supplied, host-targeted readiness replies include setup_host/doctor.host, setup prompts can target hosts like Claude Desktop, Claude 桌面, Gemini CLI, Gemini 命令行, install Codex Skill, register MCP for Claude Desktop, 安装 Codex Skill, 注册 MCP 到 Gemini 命令行, or 帮我配置 Patchbay 到 Claude 桌面, and gate-changing prompts such as approve/continue/apply without run_id return local guidance instead of choosing a run automatically.",
        "patchbay_plan": "Run the planning phase (host-agnostic — provider configurable via [phases.plan] in .ai/patchbay.toml).",
        "patchbay_approve": "Approve the plan so the writer phase can proceed.",
        "patchbay_write": "Run the implementation phase (provider configurable via [phases.write] / [writer].provider).",
        "patchbay_test": "Run test commands from the plan or allowlist inside the isolated worktree.",
        "patchbay_review": "Run the review phase (provider configurable via [phases.review]).",
        "patchbay_fix": "Run the fix phase after a CHANGES_REQUESTED review (provider defaults to write).",
        "patchbay_status": "Return current run status and artifacts, including latest cross-phase event.",
        "patchbay_context": "Return the unified handoff digest for resuming a run across MCP hosts, CLI sessions, and the web workbench, including top-level routing_evidence, efficiency_summary, and agent_activity.health_cards with safe local/diagnostic actions.",
        "patchbay_metrics": "Return only run_metrics efficiency evidence: phase durations, tier_usage economy/supervision/execution rollups, attempts, event/trace counts, provider usage, known cost/token fields, efficiency_summary for verified economy token/cost/time share, routing_evidence.economy_health including command_not_ready, and top-level actions[] mirrored from routing_evidence.actions[] for safe local_agent, command, or diagnostic_tab routing follow-ups such as configure_reasonix_command or configure_economy_provider_command; hosts may send configure economy provider command to <path> back through patchbay_agent to repair providers.<id>.command directly.",
        "patchbay_doctor": "Run unified read-only readiness checks for CLI shims, config, bundled Skill source, and Skill installation state; skips stdio MCP probing by default and returns next_actions, recommendations, and structured actions[], with host-aware concrete MCP registration actions and probe actions.",
        "patchbay_setup": "Initialize Patchbay project files, create local config, install the Codex Skill, return MCP registration guidance, include a doctor summary, and expose structured actions[] for safe follow-ups.",
        "patchbay_install": "Alias for patchbay_setup: initialize Patchbay project files, create local config, install the Codex Skill, register MCP when possible, include a doctor summary, and expose structured actions[].",
        "patchbay_skill_install": "Install only the bundled Patchbay Codex Skill into a selected skills root.",
        "patchbay_skill_print": "Return the bundled Patchbay Skill files for inspection or external installation.",
        "patchbay_skill_doctor": "Validate the bundled Patchbay Skill source and whether it is installed in the selected Codex skills root.",
        "patchbay_events": "Return the append-only event log (JSONL stream) for a run so any host can see what every phase/agent did.",
        "patchbay_trace": "Return the structured trace log (JSONL stream) for lower-level agent/tool activity with redacted raw payloads.",
        "patchbay_runs": "List recent Patchbay runs.",
        "patchbay_artifact": "Read a run artifact such as PLAN.md, TEST.log, REVIEW.md, or FINAL.diff.",
        "patchbay_config_show": "Show the effective Patchbay configuration.",
        "patchbay_config_phase_set": "Set a phase provider/model/command key without hand-editing TOML.",
        "patchbay_config_command_set": "Set a command alias in .ai/patchbay.toml.",
        "patchbay_config_test_add": "Add a test command to both allowlist and phase config.",
        "patchbay_config_profile_apply": "Apply a recommended routing profile; economy keeps expensive thinking in plan/review and routes write/fix work to Reasonix/DeepSeek, returning structured actions[] for safe readiness/start/configure_reasonix_command follow-ups.",
        "patchbay_config_profile_show": "Show whether the current write/fix routing matches the economy profile and return structured actions[] for safe apply/readiness/start/configure_reasonix_command follow-ups.",
        "patchbay_config_provider_add_cli": "Add a custom CLI provider block under [providers.<id>]; optionally activate it as the economy write/fix route for low-cost DeepSeek-style writer work.",
        "patchbay_diff": "Return the current FINAL.diff for the run.",
        "patchbay_apply": "Apply the reviewed patch to the original repository (no LLM executor).",
    }
    description = descriptions.get(name, name.replace("_", " "))
    if name in LEGACY_TOOLS:
        description += " (legacy ai-flow alias — use patchbay_* names for new integrations)"
    return {
        "name": name,
        "description": description,
        "inputSchema": {
            "type": "object",
            "properties": properties,
            "required": required,
        },
    }


def _response(request_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def handle(message: dict[str, Any]) -> dict[str, Any] | None:
    method = message.get("method")
    request_id = message.get("id")
    params = message.get("params") or {}
    if method == "initialize":
        return _response(
            request_id,
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            },
        )
    if method == "notifications/initialized":
        return None
    if method == "tools/list":
        return _response(request_id, {"tools": [_tool_schema(name) for name in TOOLS]})
    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if name not in TOOLS:
            return _error(request_id, -32601, f"Unknown tool: {name}")
        try:
            result = TOOLS[name](**arguments)
        except Exception as exc:
            return _response(
                request_id,
                {
                    "content": [{"type": "text", "text": f"ERROR: {exc}"}],
                    "isError": True,
                },
            )
        return _response(
            request_id,
            {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True),
                    }
                ]
            },
        )
    return _error(request_id, -32601, f"Unknown method: {method}")


def main() -> int:
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            message = json.loads(line)
            response = handle(message)
        except Exception as exc:
            response = _error(None, -32700, str(exc))
        if response is not None:
            print(json.dumps(response, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
