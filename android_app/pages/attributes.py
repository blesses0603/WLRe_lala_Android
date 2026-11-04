"""Server-backed ability viewer with explicit, guarded attribute allocation."""
from android_app.pages.general import Page
from android_app.widgets import label, field, button, row
from android_app.pages.ui_components import feature_card, status_line
from android_app.theme import style_input
from kivy.metrics import dp
from kivy.uix.textinput import TextInput
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
        summary=feature_card('角色能力', '能力值僅取自伺服器確認的角色狀態')
        self.info=status_line()
        summary.add_widget(self.info)
        self.add_widget(summary)

        editor=feature_card('分配屬性點',
                            '先輸入本次增加點數，確認後才送出')
        editor.add_widget(status_line(
            '未同步點數不視為 0；送出一次後等候伺服器同步，'
            '結果未知不可重送'))
        self.inputs={}
        self.stat_values={}
        for key,name in ATTRIBUTES:
            stat=feature_card(name)
            current=status_line('目前值：待同步')
            stat.add_widget(current)
            self.stat_values[key]=current
            control=TextInput(
                text='0',multiline=False,input_filter='int',
                input_type='number',font_size='15sp',
                size_hint_x=None,width=dp(94),size_hint_y=None,
                height=dp(48))
            style_input(control)
            self.inputs[key]=control
            decrement=button('－',lambda k=key:self._step(k,-1))
            increment=button('＋',lambda k=key:self._step(k,1))
            for part in (decrement,increment):
                part.size_hint_x=None
                part.width=dp(54)
            # The current value and its local +/- allocation draft belong
            # on the same touch card, as in the reference screen.
            draft=row(decrement,control,increment)
            draft.height=dp(48)
            stat.add_widget(draft)
            editor.add_widget(stat)
        self.available=status_line('可分配點數：等待伺服器同步', prominent=True)
        editor.add_widget(self.available)
        self.status=status_line()
        editor.add_widget(self.status)
        editor.add_widget(button('檢查並確認分配',self.allocate,56))
        self.add_widget(editor)

    def _step(self,key,delta):
        """Only change local input; real validation remains in allocate()."""
        field=self.inputs[key]
        try:
            current=int(field.text.strip() or '0')
        except ValueError:
            current=0
        field.text=str(max(0,current+delta))

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
        self.info.text = "\n".join(attribute_lines(self.state))
        player=(self.state.get('knowledge') or {}).get('player') or {}
        stats=player.get('stats') or {}
        points=stats.get('attribute_potential') if player.get('ready') else None
        self.available.text=(
            '可分配點數：{}'.format(points)
            if type(points) is int and points >= 0
            else '可分配點數：等待伺服器同步')
        for key,_ in ATTRIBUTES:
            value=stats.get(key) if player.get('ready') else None
            self.stat_values[key].text=(
                '目前值：{}'.format(value)
                if type(value) is int and value >= 0
                else '目前值：等待伺服器同步')
        self.status.text = ((self.state.get('attribute_allocation') or {}).get('status')
                            or preview_block_reason(self.state,live=self.d.live)
                            or '已同步，可以手動配點')
