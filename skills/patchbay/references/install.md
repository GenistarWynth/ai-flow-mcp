# Patchbay Installation

## CLI

From GitHub:

```bash
uvx --from git+https://github.com/GenistarWynth/patchbay-mcp patchbay init
```

From a local checkout:

```bash
python scripts/patchbay init
```

On Windows, `scripts/patchbay.cmd` avoids PowerShell execution-policy issues.

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
patchbay mcp doctor
```

Doctor starts the stdio MCP server, sends initialize/tools/list, and checks required tools such as `patchbay_agent`, `patchbay_plan`, and `patchbay_context`.

## Skill

Install the bundled Codex Skill:

```bash
patchbay skill install codex
```

The Skill teaches Codex when to use Patchbay and how to preserve the plan/apply gates. It complements the MCP server; it does not replace the MCP tools.
