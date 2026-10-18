"""Touch-first manual partner deployment; game server owns final state."""
from android_app.pages.general import Page
from android_app.widgets import label, button, row
from wlre.services.battle.companions import problem
from wlre.services.items.combat_resources import CAT


def companion_rows(state):
    knowledge = state.get("knowledge", {})
    current = knowledge.get("active_npc_id")
    result = []
    for index, p in sorted((knowledge.get("companions") or {}).items(),
                           key=lambda pair: int(pair[0])):
        info = CAT["npcs"].get(str(p.get("npc_id")), {})
        stats = p.get("stats") or {}
        result.append({
            "index": int(index), "npc_id": p.get("npc_id"),
            "name": info.get("name") or p.get("name") or "夥伴 {}".format(index),
            "active": p.get("npc_id") == current,
            "level": stats.get("level", "—"),
            "hp": stats.get("hp", "—"), "max_hp": stats.get("max_hp", "—"),
            "sp": stats.get("sp", "—"), "max_sp": stats.get("max_sp", "—"),
            "faith": p.get("faith", "—"),
            "reasons": {action: problem(state, int(index), p.get("npc_id"), action)
                        for action in ("deploy", "rest")},
        })
    return result


class Companions(Page):
    def __init__(self, d):
        super().__init__(d)
        self.title = label("夥伴出戰／休息：須先停止自動戰鬥、徘徊及衝突中的活動")
        self.add_widget(self.title)
        self.info = label()
        self.add_widget(self.info)
        self.items = __import__("android_app.widgets", fromlist=["column"]).column()
        self.add_widget(self.items)
        self._signature = None

    def change(self, partner, action):
        reason = problem(self.state, partner["index"], partner["npc_id"], action)
        if reason:
            self.d.message.text = reason
            return
        self.d.send({
            "type": "companion", "index": partner["index"],
            "npc_id": partner["npc_id"], "action": action,
        }, "確認{}「{}」？切換後需等待伺服器回覆。".format(
            "出戰" if action == "deploy" else "休息", partner["name"]))

    def refresh(self):
        knowledge = self.state.get("knowledge", {})
        if not knowledge.get("companions_ready"):
            self.info.text = "等待伺服器同步夥伴清單"
            return
        rows = companion_rows(self.state)
        signature = repr((rows, self.d.live))
        if signature == self._signature:
            return
        self._signature = signature
        self.info.text = "已同步 {} 名夥伴。出戰狀態不會先行假設成功。".format(len(rows))
        self.items.clear_widgets()
        if not rows:
            self.items.add_widget(label("目前沒有已確認的夥伴"))
        for item in rows:
            status = "● 出戰中" if item["active"] else "休息中"
            self.items.add_widget(label(
                "{}｜Lv.{}｜{}\nHP {}/{} · SP {}/{} · 忠誠／好友度 {}".format(
                    item["name"], item["level"], status, item["hp"],
                    item["max_hp"], item["sp"], item["max_sp"], item["faith"])))
            actions = row(
                button("設為出戰", lambda p=item: self.change(p, "deploy")),
                button("讓夥伴休息", lambda p=item: self.change(p, "rest")))
            # Disabled actions are still explained through a visible label.
            for action, control in zip(("deploy", "rest"), reversed(actions.children)):
                control.disabled = bool(item["reasons"][action]) or not self.d.live
            self.items.add_widget(actions)
            reasons = [v for v in item["reasons"].values() if v]
            if reasons:
                self.items.add_widget(label("限制：" + "／".join(dict.fromkeys(reasons))))
