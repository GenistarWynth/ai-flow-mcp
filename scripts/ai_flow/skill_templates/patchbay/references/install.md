# Patchbay Installation

## CLI

From GitHub:

```bash
uvx --from git+https://github.com/GenistarWynth/patchbay-mcp patchbay setup --host codex
```

From a local checkout:

```bash
python scripts/patchbay setup --host codex
python scripts/patchbay install --host codex
```

On Windows, `scripts/patchbay.cmd` avoids PowerShell execution-policy issues.

`patchbay setup` and its alias `patchbay install` initialize project files, create `.ai/patchbay.toml` from the ignored example when missing, install the bundled Codex Skill, try to register the selected MCP host, and include a doctor summary. If Codex, Claude Code, or Gemini CLI is unavailable, setup returns the registration command to run manually.

The conversational agent entry point accepts the same explicit local setup intent without creating a model run:

```bash
python scripts/patchbay agent message "patchbay setup" --json
python scripts/patchbay agent message "patchbay setup for claude-desktop" --json
python scripts/patchbay agent message "install patchbay for gemini" --json
```

## MCP

Register an MCP host:

```bash
patchbay mcp install codex
patchbay mcp install claude
patchbay mcp install claude-desktop
patchbay mcp install gemini
```

Codex, Claude Code, and Gemini try to run the host registration command directly and fall back to printing it if the host CLI is unavailable. Claude Desktop writes its JSON config directly.

Verify the server:

```bash
patchbay doctor
patchbay mcp doctor
```

`patchbay doctor` is the unified read-only setup check for project initialization, phase config, CLI entry points, MCP tools, bundled Skill source, and Codex Skill installation. `patchbay mcp doctor` focuses on stdio MCP server reachability, sends initialize/tools/list, and checks required tools such as `patchbay_agent`, `patchbay_plan`, `patchbay_context`, `patchbay_metrics`, `patchbay_doctor`, and `patchbay_install`.

## Skill

Install the bundled Codex Skill:

```bash
patchbay skill install codex
```

The Skill teaches Codex when to use Patchbay and how to preserve the plan/apply gates. It complements the MCP server; it does not replace the MCP tools.
