from __future__ import annotations

from typing import Any

from .config import DEFAULT_CONFIG, route_matches_economy


def profile_routing_digest(profile_result: dict[str, Any]) -> dict[str, Any]:
    status = profile_result.get("status") if isinstance(profile_result.get("status"), dict) else profile_result
    economy = status.get("economy") if isinstance(status.get("economy"), dict) else {}
    write = phase_route_snapshot(economy.get("write") if isinstance(economy.get("write"), dict) else {})
    fix = phase_route_snapshot(economy.get("fix") if isinstance(economy.get("fix"), dict) else {})
    economy_active = bool(economy.get("matches"))
    target = phase_route_snapshot(economy.get("target") if isinstance(economy.get("target"), dict) else {})
    if isinstance(economy.get("target"), dict) and economy["target"].get("label"):
        target["label"] = str(economy["target"].get("label") or "")
    command_status = economy.get("command_status") if isinstance(economy.get("command_status"), dict) else {}
    command_not_ready = [
        phase
        for phase in ("write", "fix")
        if isinstance(command_status.get(phase), dict)
        and command_status[phase].get("required")
        and command_status[phase].get("ready") is False
    ]
    command_ready = economy.get("command_ready")
    recommendation = str(status.get("recommendation") or profile_result.get("recommendation") or "")
    return {
        "profile": status.get("profile") or profile_result.get("profile") or ("economy" if economy_active else "custom"),
        "target": target if target.get("provider") else default_economy_target(),
        "economy_configured": economy_active,
        "economy_command_ready": bool(command_ready) if command_ready is not None else None,
        "workload_policy": workload_policy(target),
        "command_not_ready_phases": command_not_ready,
        "phase_strategy": status.get("phase_strategy") or {},
        "phases": {
            "write": {
                "configured": write,
                "configured_economy": phase_is_economy(write, target),
                "command_status": command_status.get("write") if isinstance(command_status.get("write"), dict) else None,
            },
            "fix": {
                "configured": fix,
                "configured_economy": phase_is_economy(fix, target),
                "command_status": command_status.get("fix") if isinstance(command_status.get("fix"), dict) else None,
            },
        },
        "summary": profile_routing_summary(economy_active=economy_active, write=write, fix=fix),
        "recommendation": recommendation,
    }


def workload_policy(target: dict[str, Any]) -> dict[str, Any]:
    effective_target = target if target.get("provider") else default_economy_target()
    target_label = str(effective_target.get("label") or route_label(effective_target) or "the configured economy target")
    return {
        "target_label": target_label,
        "economy_phases": ["write", "fix"],
        "supervision_phases": ["plan", "review"],
        "phase_roles": {
            "plan": "supervision",
            "write": "economy",
            "fix": "economy",
            "review": "supervision",
        },
        "summary": (
            f"Simple high-volume write/fix work uses the low-cost {target_label} route; "
            "plan/review stay on supervision models."
        ),
    }


def default_economy_target() -> dict[str, str]:
    raw = DEFAULT_CONFIG["profiles"]["economy"]
    return {
        "provider": str(raw.get("provider") or ""),
        "model": str(raw.get("model") or ""),
        "label": str(raw.get("label") or ""),
    }


def phase_route_snapshot(route: dict[str, Any]) -> dict[str, Any]:
    return {
        "provider": str(route.get("provider") or ""),
        "model": str(route.get("model") or ""),
        "command_key": str(route.get("command_key") or ""),
    }


def phase_is_economy(route: dict[str, Any], target: dict[str, Any]) -> bool:
    if not target:
        target = default_economy_target()
    return route_matches_economy(route, target)


def route_label(route: dict[str, Any]) -> str:
    if route.get("label"):
        return str(route.get("label"))
    provider = str(route.get("provider") or "-")
    model = str(route.get("model") or "")
    return f"{provider} / {model}" if model else provider


def profile_routing_summary(*, economy_active: bool, write: dict[str, Any], fix: dict[str, Any]) -> str:
    prefix = "Economy routing profile is active" if economy_active else "Economy routing profile is not active"
    return f"{prefix}: write {route_label(write)}, fix {route_label(fix)}."
