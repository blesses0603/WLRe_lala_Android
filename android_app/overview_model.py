"""Shared data source for the role overview screen and floating overlay.

Return only game-core-confirmed character fields; never read login credentials.
"""
from wlre.services.items.combat_resources import CAT
from wlre.services.battle.auto_battle import summary as battle_summary
from wlre.services.world.roaming import summary as roaming_summary


def overview_model(state):
    s = state or {}
    knowledge = s.get("knowledge") or {}
    player = s.get("player") or {}
    profiles = [("角色", knowledge.get("player") or {})]

    # S19-1/4 confirms the deployed companion; S19-2 clears this ID.
    # Do not display every owned companion, or infer deployment from the
    # battle list, roster order, or an optimistic UI command.
    active_npc_id = knowledge.get("active_npc_id")
    if type(active_npc_id) is int and active_npc_id > 0:
        for partner in (knowledge.get("companions") or {}).values():
            if not isinstance(partner, dict) or partner.get("npc_id") != active_npc_id:
                continue
            name = (CAT["npcs"].get(str(active_npc_id), {}).get("name")
                    or partner.get("name") or "夥伴")
            profiles.append((name + "（出戰）", partner))
            break  # At most one confirmed deployed companion.

    battle_active = bool((s.get("battle") or {}).get("active"))
    units = tuple((s.get("battle_units") or {}).values()) if battle_active else ()
    result = []
    for name, profile in profiles:
        stats = dict(profile.get("stats") or {})
        if battle_active:
            identity = profile.get("npc_id", player.get("role_id"))
            unit = next((u for u in units if identity is not None and u.get("pid") == identity), {})
            stats.update({key: unit[key] for key in ("hp", "max_hp", "sp", "max_sp", "level")
                          if key in unit})
        result.append({
            "name": name,
            **{key: stats.get(key, "—")
               for key in ("level", "hp", "max_hp", "sp", "max_sp")},
        })

    return {
        "character": player.get("name") or "等待角色同步",
        "profiles": result,
        "statuses": {
            "battle": battle_summary(s.get("auto_battle") or {}),
            "roaming": roaming_summary(s.get("roaming") or {}),
            "event": "等待伺服器事件結束" if (s.get("event_flow") or {}).get("blocked") else "待機",
            "alchemy": (s.get("alchemy") or {}).get("status", "待同步"),
            "crafting": (s.get("crafting") or {}).get("status", "待同步"),
            "supply": str(((s.get("inventory") or {}).get("field_supply") or {}).get("reason", "尚無紀錄")),
            "expedition": (s.get("expedition") or {}).get("status", "等待資料同步"),
            "maintenance": (s.get("maintenance") or {}).get("status", "等待戰後檢查"),
        },
    }


def overview_lines(state):
    """Keep the original mobile 角色概況 field names and ordering."""
    data = overview_model(state)
    rows = [str(data["character"])]
    for p in data["profiles"]:
        rows.append("{} Lv.{}\nHP {}/{} · SP {}/{}".format(
            p["name"], p["level"], p["hp"], p["max_hp"], p["sp"], p["max_sp"]))
    for key, label in (
        ("battle", "自動戰鬥"), ("roaming", "自動徘徊"), ("event", "事件"),
        ("alchemy", "煉金"), ("crafting", "製作"), ("supply", "補給"),
        ("expedition", "遠征"), ("maintenance", "修理／整理"),
    ):
        rows.append(label + "：" + str(data["statuses"][key]))
    return rows
