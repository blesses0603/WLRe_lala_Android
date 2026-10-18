"""Desktop-parity bag model without importing Tkinter on Android.

Only server-confirmed inventory slots appear. Detail fields never guess
unknown bonus types; core validates actual item actions separately.
"""
from wlre.services.items.combat_resources import CAT, item_name, heal_effects, available

# Desktop's current 6x4 layout is adapted to 4x6 for narrow touch screens.
# Both display 24 verified slots per page, using larger original item icons.
PAGE_SIZE = 24
COLUMNS = 4
ICON_SIZE = 64


def visible_items(inventory, query=""):
    query = query.strip().casefold()
    result = []
    for index, record in sorted(
            (inventory.get("items") or {}).items(), key=lambda pair: int(pair[0])):
        sid = record.get("item_id")
        name = item_name(sid)
        if query and query not in (name + " " + str(sid)).casefold():
            continue
        result.append((str(index), record, name))
    return result


def item_details(inventory, index, record):
    sid = record["item_id"]
    info = CAT["items"].get(str(sid), {})
    effects = heal_effects(sid)
    lines = ["HP +{}".format(effects["hp"])] if effects.get("hp") else []
    if effects.get("sp"):
        lines.append("SP +{}".format(effects["sp"]))
    if not lines:
        lines = [
            "屬性碼 {}：值 {}".format(attr["kind"], attr["value"])
            for attr in info.get("attributes", [])
            if attr.get("kind") and attr.get("value") not in (0, 100)
        ][:4]
    return {
        "id": sid, "name": item_name(sid), "index": int(index),
        "count": record.get("count", 0),
        "reserved": inventory.get("reserved", {}).get(str(index), 0),
        "available": available(inventory, str(index)),
        "kind": info.get("kind"),
        "effects": effects,
        "lines": lines or ["尚無已確認的可顯示效果"],
    }
