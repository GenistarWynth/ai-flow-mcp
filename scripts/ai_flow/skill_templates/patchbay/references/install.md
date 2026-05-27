# Patchbay Installation

## CLI

From GitHub:

```bash
uvx --from git+https://github.com/GenistarWynth/patchbay-mcp patchbay setup --host codex
```

From a local checkout:

```bash
python scripts/patchbay setup --host codex
```

On Windows, `scripts/patchbay.cmd` avoids PowerShell execution-policy issues.

`patchbay setup` initializes project files, creates `.ai/patchbay.toml` from the ignored example when missing, installs the bundled Codex Skill, returns MCP registration guidance for the selected host, and includes a doctor summary.

The conversational agent entry point accepts the same explicit local setup intent without creating a model run:

```bash
python scripts/patchbay agent message "patchbay setup" --json
```

## MCP

Print or write host registration:

```bash
patchbay mcp install codex
patchbay mcp install claude
patchbay mcp install claude-desktop
patchbay mcp install gemini
```

Codex, Claude Code, and Gemini currently print the host command to run. Claude Desktop writes its JSON config directly.

Verify the server:

```bash
patchbay doctor
patchbay mcp doctor
```

`patchbay doctor` is the unified read-only setup check for project initialization, phase config, CLI entry points, MCP tools, bundled Skill source, and Codex Skill installation. `patchbay mcp doctor` focuses on stdio MCP server reachability, sends initialize/tools/list, and checks required tools such as `patchbay_agent`, `patchbay_plan`, `patchbay_context`, `patchbay_metrics`, and `patchbay_doctor`.

## Skill

Install the bundled Codex Skill:

```bash
patchbay skill install codex
```

The Skill teaches Codex when to use Patchbay and how to preserve the plan/apply gates. It complements the MCP server; it does not replace the MCP tools.
