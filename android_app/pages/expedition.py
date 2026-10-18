"""Android expedition controls driven solely by the official 1262 shared core."""
import copy
import time

from android_app.pages.general import Page
from android_app.widgets import label, button, row, field, check, column, pick
from wlre.services.expedition import (preferences as expedition_defaults,
                                      validate, recovery_stock, faith_gain, duration)
from wlre.services.expedition_data import load_catalog
from wlre.services.items.combat_resources import CAT, item_name
from android_app.expedition_display import task_name, time_text, rewards_text


def available_quests(state, catalog, min_hours=0):
    """Only server-advertised, level-eligible quests; never hallucinate tasks."""
    data = state.get("expedition") or {}
    level = catalog.get("levels", {}).get(str(data.get("level")))
    if not level:
        return []
    result = []
    for sid in sorted(set(data.get("quests", {}).values())):
        item = catalog.get("tasks", {}).get(str(sid))
        if (item and item["difficulty"] <= level["difficulty"]
                and duration(item, level) > min_hours * 3600):
            result.append((item, duration(item, level)))
    return result


class Expedition(Page):
    def __init__(self, d):
        super().__init__(d)
        self.catalog = load_catalog()
        self.settings_loaded = False
        default = expedition_defaults()
        self.hours = field(self, "任務時間大於幾小時（0～24）", default["min_hours"])
        self.success = field(self, "最低派遣成功率（0～100%）", default["min_success"])
        self.faith = field(self, "最低好友度（1～100）", default["faith_min"], True)
        self.recovery_id = 0
        self.restore_label = label("好友度物品：自動從背包選擇")
        self.add_widget(self.restore_label)
        self.add_widget(button("選擇背包好友度恢復物品", self.choose_restore))
        self.auto_claim = check(self, "到期自動領獎（確認入包後再派遣）", True)
        self.add_widget(row(
            button("保存遠征設定", self.save),
            button("啟動自動派遣", self.start),
            button("停止遠征", self.stop)))
        self.status = label("等待遠征與駐紮所資料同步")
        self.add_widget(self.status)
        self.team_status = label()
        self.add_widget(self.team_status)
        self.items = column()
        self.add_widget(label("目前可用的任務（依伺服器同步與官方資料）"))
        self.add_widget(self.items)
        self.roles = label()
        self.add_widget(self.roles)
        self.signature = None
        self.current = None

    def read_settings(self):
        try:
            value = {
                "min_hours": float(self.hours.text),
                "min_success": float(self.success.text),
                "faith_min": int(self.faith.text),
                "item_id": self.recovery_id,
                "auto_claim": bool(self.auto_claim.active),
            }
            return validate(value)
        except (ValueError, TypeError) as error:
            self.d.message.text = "遠征設定有誤：" + str(error)
            return None

    def load_settings(self, settings):
        value = validate(settings)
        self.hours.text = str(value["min_hours"])
        self.success.text = str(value["min_success"])
        self.faith.text = str(value["faith_min"])
        self.recovery_id = value["item_id"]
        self.auto_claim.active = value["auto_claim"]
        self.restore_label.text = ("好友度物品：自動從背包選擇" if not self.recovery_id
                                   else "好友度物品：" + item_name(self.recovery_id))
        self.settings_loaded = True

    def save(self):
        checked = self.read_settings()
        if checked is None:
            return False
        preferences = copy.deepcopy(self.d.data.get("preferences") or {})
        preferences["expedition"] = checked
        if self.d.preferences(preferences):
            self.d.message.text = "遠征設定已交由本帳號服務保存，不會自動啟動"
            return True
        return False

    def start(self):
        checked = self.read_settings()
        if checked is None or not self.save():
            return
        self.d.send({"type": "start_expedition", "settings": checked},
                    "確認啟動遠征自動派遣？可能使用好友度物品，並依設定派遣與領獎。")

    def stop(self):
        self.d.send({"type": "stop_expedition"})

    def choose_restore(self):
        stocks = recovery_stock(self.state.get("inventory") or {})
        entries = [(0, "自動從背包挑選（不解除鎖定）")]
        entries.extend((sid, "{}｜好友度 +{}｜可用 {}".format(
            item_name(sid), faith_gain(sid), count))
            for sid, count in sorted(stocks.items()))
        if self.recovery_id and self.recovery_id not in stocks:
            entries.append((self.recovery_id, "指定種類缺貨：" + item_name(self.recovery_id)))
        def commit(value):
            self.recovery_id = value
            self.restore_label.text = ("好友度物品：自動從背包選擇" if not value
                                       else "好友度物品：" + item_name(value))
        pick("背包好友度恢復物品", entries, commit)

    def detail(self, quest, seconds):
        self.current = quest["id"]
        self.status.text = ("{}｜所需 {}｜消耗好友度 {}\n\n"
                            "任務獎勵：{}").format(
            task_name(quest), time_text(seconds), quest["faith_cost"],
            rewards_text(quest))

    def refresh(self):
        if not self.settings_loaded and "preferences" in self.d.data:
            self.load_settings((self.d.data["preferences"] or {}).get(
                "expedition", expedition_defaults()))
        e = self.state.get("expedition") or {}
        if not e.get("ready") or not e.get("outpost_ready"):
            self.status.text = "等待伺服器遠征與駐紮所資料同步；未手動啟動前不會派遣"
        elif e.get("uncertain"):
            self.status.text = "有遠征操作結果未確認，請重新登入同步，切勿重複派遣"
        else:
            self.status.text = str(e.get("status") or "遠征已同步，等待手動啟動")
        info = []
        for team in e.get("teams", {}).values():
            if not team.get("quest"):
                continue
            quest = self.catalog.get("tasks", {}).get(str(team["quest"]), {})
            remaining = max(0, team.get("due", 0) - time.monotonic())
            info.append("隊伍 {}：{}｜{}".format(
                team["index"], task_name(quest),
                time_text(remaining) if remaining else "等待結算"))
        self.team_status.text = ("進行中的遠征：\n" + "\n".join(info)
                                 if info else "目前沒有已同步的進行中遠征")
        self.team_status.text += "\n已自動領獎 {} 次".format(e.get("claimed", 0))
        roles = e.get("roles") or {}
        self.roles.text = "駐紮所：" + (", ".join(
            "{}（好友度 {}，{}）".format(
                CAT["npcs"].get(str(x.get("npc_id")), {}).get("name", "夥伴"),
                x.get("faith", "—"), "閒置" if x.get("state") == 0 else "遠征中")
            for x in roles.values()) or "等待駐紮所夥伴資料")
        try:
            hours = float(self.hours.text)
        except ValueError:
            hours = 0
        quests = available_quests(self.state, self.catalog, hours)
        signature = (tuple((q["id"], seconds) for q, seconds in quests),
                     self.current)
        if signature != self.signature:
            self.signature = signature
            self.items.clear_widgets()
            if not quests:
                self.items.add_widget(label("尚無符合條件且已同步的任務"))
            for quest, seconds in quests[:50]:
                self.items.add_widget(button(
                    "{}｜{}｜好友度 {}".format(
                        task_name(quest), time_text(seconds), quest["faith_cost"]),
                    lambda q=quest, t=seconds: self.detail(q, t), 62))
