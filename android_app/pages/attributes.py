"""Server-backed attribute display. Allocation commands are deliberately disabled."""
from android_app.pages.general import Page
from android_app.widgets import label

ATTRIBUTES = (("int", "智力 INT"), ("str", "力量 STR"),
              ("con", "體質 CON"), ("agi", "敏捷 AGI"),
              ("wis", "智慧 WIS"))


def attribute_lines(state):
    knowledge = (state or {}).get("knowledge") or {}
    player = knowledge.get("player") or {}
    stats = player.get("stats") or {}
    if not player.get("ready"):
        return ["角色能力尚未由伺服器完整同步。", "未同步的點數不會顯示成 0。"]
    result = []
    for field, name in ATTRIBUTES:
        value = stats.get(field)
        result.append("{}：{}".format(
            name, value if type(value) is int and value >= 0 else "待同步"))
    points = stats.get("attribute_potential")
    result.append("剩餘可配點：{}".format(
        points if type(points) is int and points >= 0 else "待同步"))
    return result


class Attributes(Page):
    def __init__(self, dashboard):
        super().__init__(dashboard)
        self.add_widget(label("角色能力｜伺服器已確認資訊"))
        self.info = label()
        self.add_widget(self.info)
        self.add_widget(label(
            "目前僅顯示能力值與剩餘點數。Android 配點封包／回覆驗證尚未移植，"
            "為避免誤扣點數，本頁沒有配點或重送按鈕。"))

    def refresh(self):
        self.info.text = "\n\n".join(attribute_lines(self.state))
