"""Server-backed ability viewer with explicit, guarded attribute allocation."""
from android_app.pages.general import Page
from android_app.widgets import label, field, button
from wlre.services.battle.attribute_points import baseline, preview_block_reason

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
            "僅以伺服器已同步的五項能力作為基準；送出一次後等成功回覆及能力同步。"
            " 結果不明時請重新登入，不會自動重送。"))
        self.inputs = {key: field(self, name + '（本次增加點數）', '0', numeric=True)
                       for key, name in ATTRIBUTES}
        self.status = label()
        self.add_widget(self.status)
        self.add_widget(button('檢查並確認分配', self.allocate))

    def allocate(self):
        reason = preview_block_reason(self.state, live=self.d.live)
        if reason:
            self.d.message.text = reason
            return
        try:
            increments = {key: int(view.text.strip() or '0')
                          for key, view in self.inputs.items()}
            current = baseline((self.state['knowledge']['player'] or {})['stats'])
        except (ValueError, KeyError, TypeError) as exc:
            self.d.message.text = '能力數值不完整或輸入有誤：' + type(exc).__name__
            return
        total = sum(increments.values())
        if total <= 0 or total > current['attribute_potential']:
            self.d.message.text = '本次配點至少 1 點且不得超出伺服器剩餘點數'
            return
        description = '本次確定分配 {} 點：\n{}\n\n送出後必須等待伺服器同步，禁止重送。'.format(
            total, '、'.join('{} +{}'.format(key.upper(), n)
                             for key, n in increments.items() if n > 0))
        self.d.send({'type':'allocate_points','increments':increments,
                     'baseline':current}, description)

    def refresh(self):
        self.info.text = "\n\n".join(attribute_lines(self.state))
        self.status.text = ((self.state.get('attribute_allocation') or {}).get('status')
                            or preview_block_reason(self.state,live=self.d.live)
                            or '已同步，可以手動配點')
