from __future__ import annotations

import json
from typing import Any


INPUT_TOKEN_KEYS = {"input_tokens", "prompt_tokens"}
OUTPUT_TOKEN_KEYS = {"output_tokens", "completion_tokens"}
CACHED_TOKEN_KEYS = {"cache_creation_input_tokens", "cache_read_input_tokens", "cached_tokens"}
TOTAL_TOKEN_KEYS = {"total_tokens"}
COST_KEYS = {"cost", "cost_usd", "estimated_cost_usd", "estimated_total", "total_cost", "total_cost_usd"}


class UsageText(str):
    """String provider output with optional structured usage metadata."""

    usage_metrics: dict[str, Any]

    def __new__(cls, value: str, usage_metrics: dict[str, Any] | None = None) -> "UsageText":
        obj = str.__new__(cls, value)
        obj.usage_metrics = usage_metrics or empty_usage_metrics()
        return obj


def empty_usage_metrics() -> dict[str, Any]:
    return {
        "token_usage": {
            "known": False,
            "input_tokens": None,
            "output_tokens": None,
            "cached_tokens": None,
            "total_tokens": None,
        },
        "cost": {
            "known": False,
            "currency": "USD",
            "estimated_total": None,
        },
    }


def with_usage(text: str, metrics: dict[str, Any] | None) -> UsageText:
    return UsageText(text, metrics if usage_known(metrics) else None)


def usage_known(metrics: dict[str, Any] | None) -> bool:
    if not metrics:
        return False
    token_usage = metrics.get("token_usage") if isinstance(metrics, dict) else None
    cost = metrics.get("cost") if isinstance(metrics, dict) else None
    return bool(
        isinstance(token_usage, dict)
        and token_usage.get("known")
        or isinstance(cost, dict)
        and cost.get("known")
    )


def metrics_from_output(output: Any) -> dict[str, Any]:
    attached = getattr(output, "usage_metrics", None)
    if usage_known(attached):
        return attached
    if isinstance(output, str):
        return metrics_from_text(output)
    return metrics_from_value(output)


def metrics_from_text(text: str) -> dict[str, Any]:
    events: list[Any] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or not stripped.startswith(("{", "[")):
            continue
        try:
            events.append(json.loads(stripped))
        except json.JSONDecodeError:
            continue

    result_events = [event for event in events if isinstance(event, dict) and event.get("type") == "result"]
    if not result_events:
        result_events = [
            event
            for event in events
            if isinstance(event, dict)
            and any(key in event for key in ("usage", "total_cost_usd", "cost_usd", "estimated_cost_usd"))
        ]
    return merge_usage_metrics(*(metrics_from_value(event) for event in (result_events or events)))


def metrics_from_json_text(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if not stripped:
        return empty_usage_metrics()
    try:
        return metrics_from_value(json.loads(stripped))
    except json.JSONDecodeError:
        return metrics_from_text(text)


def metrics_from_value(value: Any) -> dict[str, Any]:
    accumulator = _UsageAccumulator()
    _visit_usage(value, accumulator)
    return accumulator.as_metrics()


def merge_usage_metrics(*items: dict[str, Any] | None) -> dict[str, Any]:
    accumulator = _UsageAccumulator()
    for item in items:
        if not isinstance(item, dict):
            continue
        token_usage = item.get("token_usage")
        if isinstance(token_usage, dict):
            accumulator.add_tokens(
                input_tokens=_to_int(token_usage.get("input_tokens")),
                output_tokens=_to_int(token_usage.get("output_tokens")),
                cached_tokens=_to_int(token_usage.get("cached_tokens")),
                total_tokens=_to_int(token_usage.get("total_tokens")),
            )
        cost = item.get("cost")
        if isinstance(cost, dict):
            accumulator.add_cost(_to_float(cost.get("estimated_total")), str(cost.get("currency") or "USD"))
    return accumulator.as_metrics()


def event_usage_kwargs(output: Any) -> dict[str, Any]:
    metrics = metrics_from_output(output)
    if not usage_known(metrics):
        return {}
    result: dict[str, Any] = {}
    token_usage = metrics.get("token_usage")
    if isinstance(token_usage, dict) and token_usage.get("known"):
        result["token_usage"] = {
            key: value
            for key, value in token_usage.items()
            if key != "known" and value is not None
        }
    cost = metrics.get("cost")
    if isinstance(cost, dict) and cost.get("known"):
        result["cost"] = {
            "currency": cost.get("currency") or "USD",
            "estimated_total": cost.get("estimated_total"),
        }
    return result


class _UsageAccumulator:
    def __init__(self) -> None:
        self.input_tokens = 0
        self.output_tokens = 0
        self.cached_tokens = 0
        self.total_tokens = 0
        self.input_known = False
        self.output_known = False
        self.cached_known = False
        self.total_known = False
        self.cost_total = 0.0
        self.cost_known = False
        self.currency = "USD"

    def add_tokens(
        self,
        *,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        cached_tokens: int | None = None,
        total_tokens: int | None = None,
    ) -> None:
        if input_tokens is not None:
            self.input_tokens += input_tokens
            self.input_known = True
        if output_tokens is not None:
            self.output_tokens += output_tokens
            self.output_known = True
        if cached_tokens is not None:
            self.cached_tokens += cached_tokens
            self.cached_known = True
        if total_tokens is not None:
            self.total_tokens += total_tokens
            self.total_known = True

    def add_cost(self, value: float | None, currency: str = "USD") -> None:
        if value is None:
            return
        self.cost_total += value
        self.cost_known = True
        if currency:
            self.currency = currency

    def as_metrics(self) -> dict[str, Any]:
        total_tokens = self.total_tokens if self.total_known else None
        if total_tokens is None and (self.input_known or self.output_known or self.cached_known):
            total_tokens = self.input_tokens + self.output_tokens + self.cached_tokens
        return {
            "token_usage": {
                "known": self.input_known or self.output_known or self.cached_known or self.total_known,
                "input_tokens": self.input_tokens if self.input_known else None,
                "output_tokens": self.output_tokens if self.output_known else None,
                "cached_tokens": self.cached_tokens if self.cached_known else None,
                "total_tokens": total_tokens,
            },
            "cost": {
                "known": self.cost_known,
                "currency": self.currency,
                "estimated_total": round(self.cost_total, 6) if self.cost_known else None,
            },
        }


def _visit_usage(value: Any, accumulator: _UsageAccumulator) -> None:
    if isinstance(value, dict):
        input_tokens = _sum_keys(value, INPUT_TOKEN_KEYS)
        output_tokens = _sum_keys(value, OUTPUT_TOKEN_KEYS)
        cached_tokens = _sum_keys(value, CACHED_TOKEN_KEYS)
        total_tokens = _sum_keys(value, TOTAL_TOKEN_KEYS)
        if any(item is not None for item in (input_tokens, output_tokens, cached_tokens, total_tokens)):
            accumulator.add_tokens(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cached_tokens=cached_tokens,
                total_tokens=total_tokens,
            )
        cost_value = _first_float(value, COST_KEYS)
        if cost_value is not None:
            accumulator.add_cost(cost_value, _currency_for(value))
        for nested in value.values():
            _visit_usage(nested, accumulator)
    elif isinstance(value, list):
        for item in value:
            _visit_usage(item, accumulator)


def _sum_keys(value: dict[str, Any], keys: set[str]) -> int | None:
    total = 0
    known = False
    for key in keys:
        parsed = _to_int(value.get(key))
        if parsed is not None:
            total += parsed
            known = True
    return total if known else None


def _first_float(value: dict[str, Any], keys: set[str]) -> float | None:
    for key in keys:
        parsed = _to_float(value.get(key))
        if parsed is not None:
            return parsed
    return None


def _currency_for(value: dict[str, Any]) -> str:
    currency = str(value.get("currency") or value.get("cost_currency") or "").strip().upper()
    return currency or "USD"


def _to_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _to_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None
