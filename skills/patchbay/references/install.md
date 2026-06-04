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
python scripts/patchbay setup --host codex --no-mcp
python scripts/patchbay install --host codex
python scripts/patchbay doctor --local-only --json
```

On Windows, `scripts/patchbay.cmd` avoids PowerShell execution-policy issues.

`patchbay setup` and its alias `patchbay install` initialize project files, create `.ai/patchbay.toml` from the ignored example when missing, install the bundled Codex Skill, try to register the selected MCP host, include a doctor summary, and return safe `actions[]` plus `action_groups[]` for follow-ups. Setup, doctor, and `mcp install` normalize common host names such as `Claude Desktop`, `Claude 桌面`, `claude-desktop`, `Claude Code`, `Claude 代码`, `Gemini CLI`, and `Gemini 命令行`. If Codex, Claude Code, or Gemini CLI is unavailable, setup returns the registration command to run manually.

The conversational agent entry point accepts the same explicit local setup intent without creating a model run:

```bash
python scripts/patchbay agent message "patchbay setup" --json
python scripts/patchbay agent message "patchbay setup for Claude Desktop" --json
python scripts/patchbay agent message "install patchbay for Gemini CLI" --json
python scripts/patchbay agent message "install Codex Skill" --json
python scripts/patchbay agent message "register MCP for Claude Desktop" --json
python scripts/patchbay agent message "patchbay setup without MCP" --json
python scripts/patchbay agent message "走本地模式，不走 MCP" --json
python scripts/patchbay agent message "configure DeepSeek provider" --json
python scripts/patchbay agent message "configure DeepSeek provider to <command>" --json
python scripts/patchbay agent message "简单 writer/fix 用 DeepSeek 省钱" --json
python scripts/patchbay agent message "降本，让简单 writer/fix 走低价模型" --json
python scripts/patchbay agent message "configure reasonix command" --json
python scripts/patchbay agent message "configure reasonix command to <path>" --json
```

Setup scope is prompt-aware: `install Codex Skill` installs the Skill without attempting MCP registration, `register MCP for Claude Desktop` skips Skill installation, and `patchbay setup without MCP` / `--skip-mcp` / `--no-mcp` / `--local-only` keeps setup local to project files and Skill installation. Phrases such as `please don't use MCP`, `no MCP`, `use Chrome Skill instead of MCP`, `少用这个MCP`, `不要用这个MCP`, `不走 MCP`, `走本地模式`, or `只用本地工具` are treated as local-only setup too. The same scope applies to `readiness` / `doctor`; `readiness without MCP`, `patchbay doctor --local-only`, and `patchbay_doctor(skip_mcp=true)` hide MCP probe/register follow-up actions from the conversational response. Web workbench clients should persist a selected local-only/no-MCP preference, restore it after refresh/reopen, start doctor with `skip_mcp=true`, and rewrite ordinary host setup actions such as `patchbay setup for claude-desktop` into `patchbay setup without MCP for claude-desktop`.

Use `configure DeepSeek provider` when you need a copyable template for registering a custom low-cost writer. Readiness may surface this action alongside `configure_reasonix_command` when the built-in Reasonix/DeepSeek route is configured but not executable; desktop/Web Readiness UIs may render a guarded economy-provider form only from that structured action, not from healthy readiness alone. Use `configure DeepSeek provider to <command>` when the local DeepSeek wrapper is known; it registers `cheap_writer`, activates write/fix economy routing, and keeps plan/review on the stronger configured providers. Mixed prompts such as `简单 writer/fix 用 DeepSeek 省钱` or `降本，让简单 writer/fix 走低价模型` also apply the economy profile without creating a run. If readiness or metrics report a custom provider command failure, send `configure economy provider command to <path>` or inspect `providers.<id>.command` and copy the returned `configure_economy_provider_command`; Reasonix-specific fixes only apply to the built-in `reasonix_cli` economy target.

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

`patchbay doctor` is the unified read-only setup check for project initialization, phase config, CLI entry points, bundled Skill source, whether the installed Codex Skill matches that source, MCP follow-up actions, and economy-route command readiness. It skips stdio MCP probing by default; add `--local-only` when you also want to hide MCP probe/register follow-up actions. It returns safe `actions[]` and `action_groups[]`; when the Skill is missing or outdated and no custom skills path is selected, `install_skill` is returned as a safe `local_agent` action with message `install Codex Skill` and a `patchbay skill install codex` command fallback. With a custom Skill path, it remains a command action so the selected destination is preserved. `patchbay doctor --probe-mcp` and `patchbay mcp doctor` focus on stdio MCP server reachability, send initialize/tools/list, and check required tools such as `patchbay_agent`, `patchbay_plan`, `patchbay_context`, `patchbay_metrics`, `patchbay_doctor`, `patchbay_cancel`, `patchbay_install`, `patchbay_skill_install`, and `patchbay_skill_doctor`.

After registration, restart or reload hosts that cache MCP tool lists. Verify that `patchbay_agent` is visible in the host before starting a gated run.

## Skill

Install the bundled Codex Skill:

```bash
patchbay skill install codex
patchbay skill doctor codex
```

The host argument may be `codex` or a Codex alias such as `Codex Desktop`, `Codex CLI`, or `Codex 桌面`; output is normalized to `codex`.

The default destination is `$CODEX_HOME/skills` or `~/.codex/skills`. `patchbay skill doctor` validates both the bundled Skill source and the installed copy; stale installs return `status: "outdated"`, `installed_matches_source: false`, `missing_installed_files`, `changed_installed_files`, `extra_installed_files`, and a safe reinstall action. The Skill triggers on phrases such as "走多模型流程" and "multi-agent workflow". It can use MCP tools when they are available, or the local CLI path when the user or host asks for no-MCP work.
