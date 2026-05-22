from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from ..errors import AiFlowError
from ..artifacts import append_text
from ..runner import merged_env, redact


def run_deepseek_writer(
    *,
    prompt: str,
    config: dict,
    log_path: Path,
    command_key: str = "",
    timeout: int = 900,
    env: dict[str, str] | None = None,
) -> str:
    _ = command_key  # unused — deepseek_api is HTTP, not CLI
    deepseek_cfg = config.get("deepseek", {})
    key_env = str(deepseek_cfg.get("api_key_env", "DEEPSEEK_API_KEY"))
    effective_env = merged_env(env) or os.environ
    api_key = effective_env.get(key_env)
    reasonix_config = _read_reasonix_config()
    if not api_key:
        api_key = reasonix_config.get("apiKey")
    if not api_key:
        raise AiFlowError(
            f"DeepSeek API key is missing from {key_env} and Reasonix config.",
            stage="write",
            suggested_next_action=f"Set {key_env} or rerun write with --mock.",
        )
    base_url = str(deepseek_cfg.get("base_url") or reasonix_config.get("baseUrl") or "https://api.deepseek.com").rstrip("/")
    model = str(config.get("models", {}).get("writer", "deepseek-v4-pro"))
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "thinking": {"type": "enabled"},
        "reasoning_effort": "high",
    }
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        base_url + "/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Reasonix/0.47.0",
            "HTTP-Referer": "https://reasonix.local",
            "X-Title": "reasonix",
        },
        method="POST",
    )
    secrets = [api_key]
    append_text(log_path, f"POST {base_url}/chat/completions model={model}\n")
    try:
        with urllib.request.urlopen(request, timeout=max(timeout, 10)) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        append_text(log_path, redact(detail, extra_values=secrets) + "\n")
        raise AiFlowError(
            f"DeepSeek API returned HTTP {exc.code}.",
            stage="write",
            suggested_next_action="Check DeepSeek credentials, model name, and quota.",
        ) from exc
    except urllib.error.URLError as exc:
        raise AiFlowError(
            f"DeepSeek API request failed: {exc.reason}",
            stage="write",
            suggested_next_action="Check network access or rerun with --mock.",
        ) from exc
    append_text(log_path, redact(raw, extra_values=secrets) + "\n")
    try:
        data = json.loads(raw)
        return str(data["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise AiFlowError("DeepSeek response did not contain message content.", stage="write") from exc


def _read_reasonix_config() -> dict:
    path = Path.home() / ".reasonix" / "config.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}
