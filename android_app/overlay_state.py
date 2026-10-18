"""Privacy-safe, bounded projection of active game sessions for Android overlay.

The floating window appears over other apps, so it must NEVER expose login
passwords, raw account names, authentication payloads or chat messages.
"""
from __future__ import annotations
from android_app.overview_model import overview_model


def _mask(value):
    value = str(value or "")
    if len(value) < 3:
        return "••"
    return value[:1] + "•••" + value[-1:]


def _text(value, limit=20):
    return "".join(ch for ch in str(value or "") if ch.isprintable())[:limit]


def _connection(session):
    if not session.active or session.stop_event.is_set():
        return "已斷線"
    return {
        "connecting": "連線中",
        "role_selection": "等待選角",
        "world_ready": "角色在線",
        "disconnected": "已斷線",
    }.get(session.phase, "連線進行中")


def _battle(session):
    if not session.active or session.stop_event.is_set() or session.phase != "world_ready":
        return "AI 未運作"
    state = getattr(session, "automation", {}) or {}
    battle = state.get("battle") or {}
    if not battle.get("enabled"):
        return "AI 未啟用"
    status = str(battle.get("status") or "")
    if status in ("waiting_heal", "waiting_supply"):
        return "AI 等待補給"
    if status in ("armed", "waiting", "idle"):
        return "AI 已啟用／待命"
    if status in ("running", "fighting", "battle"):
        return "自動戰鬥中"
    return "AI 已啟用"


def _overview(state):
    """Expose only the fields from the mobile role overview page."""
    value = overview_model(state)
    profiles = [{
        "name": _text(profile["name"], 32),
        **{key: _text(profile[key], 14) for key in ("level", "hp", "max_hp", "sp", "max_sp")},
    } for profile in value["profiles"][:5]]
    return {
        "character": _text(value["character"], 32),
        "profiles": profiles,
        "remaining_profiles": max(0, len(value["profiles"]) - len(profiles)),
        "statuses": {key: _text(text, 64) for key, text in value["statuses"].items()},
    }


def snapshot(manager):
    """Read actual service-owned state, never UI-cached/optimistic state."""
    rows = []
    active = online = total = 0
    with manager.lock:
        for session in manager.sessions.values():
            with session.lock:
                total += 1
                if session.active and not session.stop_event.is_set():
                    active += 1
                    if session.phase == "world_ready":
                        online += 1
                if len(rows) < 6:
                    rows.append({
                        "name": "帳號 " + str(total) + " (" + _mask(session.account) + ")",
                        "server": _text(session.label),
                        "connection": _connection(session),
                        "battle": _battle(session),
                        "overview": _overview(getattr(session, "game_state", {}))
                            if session.active and not session.stop_event.is_set()
                            and session.phase == "world_ready" else None,
                    })
    return {"total": total, "active": active, "online": online, "accounts": rows}
