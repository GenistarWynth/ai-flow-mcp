# Custom Provider Support

> **Status: CLI baseline implemented; broader provider modes remain roadmap.**
> Runtime support now covers TOML-defined CLI providers with `roles`, `command`, `args`, `prompt_mode`, and `output_contract`, plus `patchbay config provider add-cli`. This document keeps the shipped CLI contract and the remaining HTTP/ACP/safety roadmap in one place.

## Motivation

Patchbay ships built-in providers in each role registry (`PLANNERS`, `WRITERS`, `REVIEWERS`, `FIXERS`) and can also register custom CLI providers from `.ai/patchbay.toml`. Users who want to plug in a different CLI agent can do so without editing Python adapter code. Local model servers, HTTP endpoints, and generic ACP providers remain future expansion points.

## Scope

- Shipped: TOML-driven CLI provider registration under `[providers.<id>]`.
- Shipped: `roles` capability mask using `plan`, `write`, `review`, and `fix`.
- Shipped: CLI prompt delivery through `prompt_mode = "stdin" | "arg" | "file"`.
- Shipped: output contracts `plan_json`, `review_verdict`, `writer_diff`, and `worktree_diff`.
- Shipped: phase resolution registers configured providers into the existing registries at load time.
- Roadmap: HTTP API mode, generic ACP mode, provider-specific path allowlists/denylists, execution blocking, and richer output extraction.

## Out of scope

- Shipped HTTP fallback adapter (the `deepseek_api` provider was removed — custom providers replace the need for hard-coded HTTP adapters).
- Hot-reload of provider definitions (restart required after config change).
- Provider-specific streaming protocols beyond `acp` JSON-RPC.
- Automatic provider discovery from `$PATH`.

---

## Proposed TOML Schema

Each custom provider is defined in `.ai/patchbay.toml` under a `[providers.<id>]` section:

```toml
[providers.my_writer]
# Which roles this provider can fulfill. At least one required.
roles = ["writer", "fixer"]

# Execution mode: cli_stdin | cli_stdout | http_api | acp
mode = "cli_stdin"

# The command to run. For http_api mode this is unused.
command = "my-custom-writer"

# Extra arguments appended before the prompt (cli_stdout mode) or before
# the prompt is sent to stdin (cli_stdin / acp mode).
args = ["--model", "local-model-v1", "--temperature", "0.2"]

# Working directory for the process. Defaults to the worktree root.
cwd = ""

# Timeout in seconds. Default 900.
timeout = 900

# Extra environment variables (merged with parent env).
[providers.my_writer.env]
MY_API_KEY = "env-var-name"  # value is an env-var name, not the secret itself
MY_ENDPOINT = "https://local.model/v1"

# --- Output parsing contract ---

# How to extract the final output from raw stdout.
[providers.my_writer.output]

# For cli_stdin / cli_stdout modes:
#   start / end sentinel markers that bracket the relevant output.
start_sentinel = "BEGIN_WRITER_SUMMARY"
end_sentinel = "END_WRITER_SUMMARY"

# For http_api mode:
#   JSON path (dot notation) to the response field, e.g. "choices.0.message.content".
json_path = "choices.0.message.content"

# For review providers:
#   Required prefix on the first line of the output ("PASS" or "CHANGES_REQUESTED").
#   If set, Patchbay validates the prefix before accepting the verdict.
verdict_prefix = ""  # only for reviewer providers

# --- Safety constraints ---

[providers.my_writer.safety]
# Allowlist of path prefixes the provider may write to.
# Default: the worktree root only.
path_allowlist = ["docs/", "src/"]

# Deny list of path patterns (checked against the relative path).
# Default includes: .git/, .env*, *.secret, etc.
path_deny = []

# Whether to block subprocess execution (default true).
block_execute = true

# Maximum files the provider may touch in one invocation.
max_files = 50
```

### Role mask

The `roles` field is a list. A provider can be registered for any combination:

- `"planner"` — usable as a plan-phase executor.
- `"writer"` — usable as a write-phase executor.
- `"reviewer"` — usable as a review-phase executor.
- `"fixer"` — usable as a fix-phase executor.

If a provider is referenced in a phase but doesn't list that role, Patchbay raises a configuration error at phase resolution time.

### Mode details

| Mode | Prompt delivery | Output capture | Use case |
|------|----------------|----------------|----------|
| `cli_stdin` | Prompt written to stdin, process runs to completion | stdout | Most CLI agents |
| `cli_stdout` | Prompt passed as final CLI argument | stdout | Lightweight wrappers, `-c` style |
| `http_api` | OpenAI-compatible POST to `base_url/chat/completions` | JSON response body | Local model servers, proxies |
| `acp` | JSON-RPC over stdio (ACP protocol) | ACP transcript | Agents that speak the ACP wire format |

### Usage reporting contract

For every custom CLI provider invocation, Patchbay sets `PATCHBAY_USAGE_FILE` to a JSON sidecar path inside the run directory. Wrappers can write either a JSON object or JSONL records there with OpenAI/Claude-style fields such as `usage.prompt_tokens`, `usage.completion_tokens`, `usage.input_tokens`, `usage.output_tokens`, `usage.cache_read_input_tokens`, `total_cost_usd`, or `estimated_cost_usd`.

Patchbay merges usage found in stdout, stderr, and the sidecar, then preserves it through all output contracts, including `worktree_diff`. The merged totals flow into `events.jsonl`, `patchbay metrics`, `run_metrics.provider_usage`, `run_metrics.tier_usage`, and the Web workbench efficiency panel, so cheap high-volume writer/fixer routes can be verified with actual token/cost/duration evidence instead of provider names alone. `tier_usage.economy` groups write/fix, `tier_usage.supervision` groups plan/review, and `tier_usage.execution` groups test/apply so teams can see whether simple bulk work is actually consuming the expected low-cost share.

When a custom provider is used as `[profiles.economy]`, readiness, metrics, and write/fix preflight gates also validate `providers.<id>.command`. Missing or unresolved commands are reported as `command_not_ready` with `inspect_economy_provider_command` actions and leave the run in its prior durable state, while the built-in Reasonix path continues to use the dedicated `configure_reasonix_command` action for `commands.reasonix`.

---

## Provider Registry Integration

### Current state (post-deepseek_api removal)

Registries are static module-level dicts:

```python
PLANNERS = {"claude_cli": ..., "codex_cli": ..., "gemini_cli": ..., "mock": ...}
WRITERS   = {"reasonix_cli": ..., "mock": ...}
REVIEWERS = {"claude_cli": ..., "codex_cli": ..., "gemini_cli": ..., "mock": ...}
FIXERS    = {"reasonix_cli": ..., "mock": ...}
```

### Proposed change

1. **Config loading** (`config.py`) — `load_config()` merges `[providers.*]` blocks into the config dict. Validation runs at load time:
   - Every provider has a non-empty `id`, at least one `role`, and a valid `mode`.
   - `command` is required for `cli_stdin`, `cli_stdout`, and `acp` modes.
   - `base_url` is required for `http_api` mode.
   - `output` block is required; `start_sentinel`/`end_sentinel` or `json_path` depending on mode.
   - `safety` block is optional; defaults are applied.

2. **Phase resolution** (`resolve_phase`) — After resolving the provider name for a phase, `resolve_phase` checks whether it's a built-in provider or a custom provider. For custom providers, it injects a wrapper callable into the appropriate registry (PLANNERS/WRITERS/REVIEWERS/FIXERS) keyed by the provider ID.

3. **Generic adapter** — A new `run_generic_provider()` function in `scripts/ai_flow/adapters/generic_provider.py` that:
   - Reads the provider config.
   - Builds the command line from `command` + `args`.
   - Delivers the prompt according to `mode`.
   - Captures and parses output according to the `output` contract.
   - Enforces `safety` constraints (path validation, execution blocking).
   - Returns the extracted content.

4. **Service dispatch** — No change to `_call_writer` / `review()` / `plan()` — they already look up the provider by ID in the registry. The generic adapter is registered under the custom provider's ID, so dispatch is transparent.

---

## Prompt / Template Plumbing

Custom providers receive the same prompt content as built-in providers for their phase:

- **Planner**: task + repository context.
- **Writer**: TASK.md + PLAN.md + plan.json + affected file context (+ TEST.log + REVIEW.md for repair).
- **Reviewer**: TASK.md + PLAN.md + FINAL.diff + TEST.log.

The prompt is delivered according to the provider's `mode`:
- `cli_stdin`: written to stdin.
- `cli_stdout`: appended as the last CLI argument.
- `http_api`: placed in the `messages[0].content` field.
- `acp`: sent as a `session/prompt` JSON-RPC request.

No template customization per provider in the initial implementation. Users who need different prompt formatting can wrap their CLI tool in a script.

---

## Mock Harness

The existing `--mock` flag on `plan` / `write` / `review` bypasses the provider entirely and uses the hard-coded `mock` entry in each registry.

For testing custom providers without a real backend, a new built-in provider `builtin_mock_generic` can be added that:
- Accepts the same provider config schema.
- Returns canned output that satisfies the `output` parsing contract.
- Is selectable via `provider = "mock"` (no change to existing behavior).

---

## Security Review Checklist

When implementing, every item below must be addressed:

- [ ] `command` and `args` are validated to prevent shell injection (use `shlex.split`, no `shell=True`).
- [ ] `cwd` is validated to stay inside the worktree or repository root.
- [ ] `env` values reference environment variable names, not inline secrets. The adapter resolves values from the parent environment at runtime.
- [ ] `path_allowlist` and `path_deny` patterns are compiled to regex and checked against all file paths the provider touches (read from `paths_from_patch`).
- [ ] `block_execute` is enforced: if the provider attempts to run subprocesses (detected via ACP `toolCall.kind == "execute"`), the outcome is `reject`.
- [ ] `max_files` is enforced: if the provider touches more files than allowed, the phase fails with a `SafetyError`.
- [ ] Provider output is redacted: any value from the provider's `env` that appears in stdout/stderr is replaced with `***REDACTED***` in logs.
- [ ] Provider process is killed on timeout; orphan cleanup is handled.
- [ ] Custom providers are never allowed to modify `.git/`, `.env*`, secret-like files, or paths outside the worktree (same rules as built-in providers).
- [ ] Custom providers cannot override built-in provider IDs (`reasonix_cli`, `claude_cli`, `codex_cli`, `gemini_cli`, `mock`).

---

## Test Surface

### Unit tests (new file `tests/test_custom_providers.py` or additions to `tests/test_ai_flow.py`)

1. **Config parsing**
   - Valid `[providers.*]` block produces a well-formed provider dict.
   - Missing required fields (`mode`, `command` for relevant modes, `output`) raises config error.
   - Invalid `roles` values raise config error.
   - Multiple providers can be defined and loaded.
   - Provider ID collision with a built-in provider raises config error.

2. **Generic adapter**
   - `cli_stdin` mode: prompt is written to stdin, stdout is captured and parsed.
   - `cli_stdout` mode: prompt is appended as last arg.
   - `http_api` mode: correct POST is constructed, response is parsed at `json_path`.
   - Output parsing with `start_sentinel`/`end_sentinel` extracts the correct region.
   - Output parsing with `json_path` extracts the correct field.
   - Verdict prefix validation: `PASS` / `CHANGES_REQUESTED` are accepted; anything else is rejected.
   - Timeout kills the process and raises `AiFlowError`.
   - `env` values are resolved from the parent environment at runtime.
   - Secrets in `env` values are redacted from logs.

3. **Safety enforcement**
   - Provider output that references paths outside `path_allowlist` raises `SafetyError`.
   - Provider output that references paths matching `path_deny` raises `SafetyError`.
   - `block_execute = true` rejects ACP execute tool calls.
   - `max_files` cap is enforced.

4. **Registry integration**
   - Custom provider appears in the resolved registry for its declared roles.
   - Phase resolution selects a custom provider when configured.
   - `resolve_phase` returns the correct provider ID, model, command_key, env, and timeout for a custom provider.

5. **End-to-end**
   - Full `plan → approve → write → test → review → apply` flow with a `cli_stdin` mock writer that returns a valid diff.
   - Full flow with a custom reviewer that returns `PASS` / `CHANGES_REQUESTED`.

---

## Migration Notes

- Existing `.ai/patchbay.toml` files that used the removed `deepseek_api` provider will now error with "Unknown writer provider." Users should switch to `reasonix_cli` (the default). Once custom provider support is implemented, users may define their own provider blocks under `[providers.<id>]` to restore equivalent functionality with any backend.
- The `[deepseek]` TOML section, `DEEPSEEK_API_KEY` env var, and `deepseek_api` provider ID are permanently removed. There is no compatibility shim.
- The model name string `deepseek-v4-pro` remains as the default `[models].writer` value — it is the underlying LLM consumed by Reasonix, not a provider ID.

---

## Implementation Order (proposed)

1. Config schema and validation (`config.py`).
2. Generic adapter for `cli_stdin` and `cli_stdout` modes.
3. Output parsing contract.
4. Safety enforcement layer.
5. Registry integration (`resolve_phase` changes).
6. `http_api` mode.
7. `acp` mode.
8. Mock harness.
9. Tests (unit + integration).
10. Documentation (`docs/patchbay.md`, `README.md`).
