# Patchbay Installation

## CLI

From GitHub:

```bash
uvx --from git+https://github.com/GenistarWynth/patchbay-mcp patchbay setup --host codex
uvx --from git+https://github.com/GenistarWynth/patchbay-mcp patchbay doctor
uvx --from git+https://github.com/GenistarWynth/patchbay-mcp patchbay web --port 8765
```

Open `http://127.0.0.1:8765` after starting the web workbench.

From a local checkout:

```bash
python scripts/patchbay setup --host codex
python scripts/patchbay install --host codex
```

On Windows, `scripts/patchbay.cmd` avoids PowerShell execution-policy issues.

`patchbay setup` and its alias `patchbay install` initialize project files, create `.ai/patchbay.toml` from the ignored example when missing, install the bundled Codex Skill, try to register the selected MCP host, and include a doctor summary. Setup, doctor, and `mcp install` normalize common host names such as `Claude Desktop`, `Claude 桌面`, `claude-desktop`, `Claude Code`, `Claude 代码`, `Gemini CLI`, and `Gemini 命令行`. If Codex, Claude Code, or Gemini CLI is unavailable, setup returns the registration command to run manually.

The conversational agent entry point accepts the same explicit local setup intent without creating a model run:

```bash
python scripts/patchbay agent message "patchbay setup" --json
python scripts/patchbay agent message "patchbay setup for Claude Desktop" --json
python scripts/patchbay agent message "install patchbay for Gemini CLI" --json
python scripts/patchbay agent message "configure DeepSeek provider" --json
python scripts/patchbay agent message "configure DeepSeek provider to <command>" --json
python scripts/patchbay agent message "configure reasonix command" --json
python scripts/patchbay agent message "configure reasonix command to <path>" --json
```

Use `configure DeepSeek provider` when you need a copyable template for registering a custom low-cost writer. Use `configure DeepSeek provider to <command>` when the local DeepSeek wrapper is known; it registers `cheap_writer`, activates write/fix economy routing, and keeps plan/review on the stronger configured providers. If readiness or metrics report a custom provider command failure, inspect `providers.<id>.command` or copy the returned `configure_economy_provider_command`; Reasonix-specific fixes only apply to the built-in `reasonix_cli` economy target.

Use `configure reasonix command` or `配置 Reasonix 命令` when readiness reports `economy_health.status = "command_not_ready"` or surfaces the `configure_reasonix_command` action. It sets `commands.reasonix = "reasonix"` without starting a model run; use `configure reasonix command to <path>`, `把 Reasonix 命令设为 <path>`, `patchbay_config_command_set`, or `patchbay config --set-key commands.reasonix --set-value <path>` when the executable needs a full path.

## MCP

Register an MCP host:

```bash
patchbay mcp install codex
patchbay mcp install claude
patchbay mcp install claude-desktop
patchbay mcp install gemini
```

Codex, Claude Code, and Gemini try to run the host registration command directly and fall back to printing it if the host CLI is unavailable. Claude Desktop writes its JSON config directly. For lightweight host-aware readiness, prefer `patchbay doctor --host <host> --json`; add `--probe-mcp` or use `patchbay mcp doctor` only when you specifically need stdio server reachability and tool-list evidence.

Verify the server:

```bash
patchbay doctor
patchbay doctor --probe-mcp
patchbay mcp doctor
```

`patchbay doctor` is the unified read-only setup check for project initialization, phase config, CLI entry points, bundled Skill source, Codex Skill installation, MCP follow-up actions, and economy-route command readiness. It skips stdio MCP probing by default. `patchbay doctor --probe-mcp` and `patchbay mcp doctor` focus on stdio MCP server reachability, send initialize/tools/list, and check required tools such as `patchbay_agent`, `patchbay_plan`, `patchbay_context`, `patchbay_metrics`, `patchbay_doctor`, `patchbay_install`, `patchbay_skill_install`, and `patchbay_skill_doctor`.

After registration, restart or reload hosts that cache MCP tool lists. Verify that `patchbay_agent` is visible in the host before starting a gated run.

## Skill

Install the bundled Codex Skill:

```bash
patchbay skill install codex
patchbay skill doctor codex
```

The default destination is `$CODEX_HOME/skills` or `~/.codex/skills`. The Skill triggers on phrases such as "走多模型流程" and "multi-agent workflow". It complements the MCP server; it does not replace MCP registration.
