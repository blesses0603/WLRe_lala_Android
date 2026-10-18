from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from android_app.widgets import column, label, button, select, row
from android_app.theme import surface, SURFACE
from wlre.core.efficiency import rates, progress, forecast, STAGES
from android_app.overview_model import overview_lines


class Page(BoxLayout):
    def __init__(self, dashboard):
        super().__init__(orientation='vertical', size_hint_y=None, spacing=dp(12), padding=dp(14))
        surface(self, color=SURFACE, radius=20)
        self.bind(minimum_height=self.setter('height'))
        self.d = dashboard; self.key = None
    @property
    def state(self): return self.d.state
    def refresh(self): pass


class Overview(Page):
    def __init__(self, d):
        super().__init__(d); self.info = label(); self.add_widget(self.info)
        from android_app.automation_ui import toggle
        self.add_widget(row(button('切換自動戰鬥', lambda: toggle(d.app, d.sid, 'battle')),
                            button('切換自動徘徊', lambda: toggle(d.app, d.sid, 'roaming'))))
        self.add_widget(button('開啟完整 AI／補給設定', lambda: setattr(d.navigation, 'text', 'AI與補給設定')))
    def refresh(self):
        self.info.text = '\n\n'.join(overview_lines(self.state))


class Events(Page):
    def __init__(self, d):
        super().__init__(d); self.info = label(); self.add_widget(self.info)
    def refresh(self): self.info.text = '\n'.join(self.d.data.get('log', [])) or '尚無事件紀錄'


class Efficiency(Page):
    def __init__(self, d):
        super().__init__(d)
        self.subject = select(self, '統計對象', ['等待資料']); self.subject.bind(text=lambda *_: self.render())
        self.unit = select(self, '效率單位', ['分', '時', '天', '秒']); self.unit.bind(text=lambda *_: self.render())
        self.info = label(); self.add_widget(self.info)
        self.add_widget(button('重新統計', lambda: d.send({'type': 'reset_efficiency'}, '重設本帳號的經驗效率統計？')))
        self.lookup = {}
    def refresh(self):
        self.lookup = {r['name']+'｜'+key: r for key, r in self.state.get('efficiency', {}).get('rows', {}).items()}
        self.subject.values = list(self.lookup)
        if self.subject.text not in self.lookup and self.lookup: self.subject.text = next(iter(self.lookup))
        self.render()
    def render(self):
        r = self.lookup.get(self.subject.text)
        if not r: self.info.text = '等待角色經驗資料；首場作為基準'; return
        remaining, percent, reborn = progress(r['exp'], r['level'], r['degree']) if all(r.get(k) is not None for k in ('exp', 'level', 'degree')) else (None, None, None)
        import time
        elapsed = max(0, time.monotonic()-r['last_time']) if self.d.live and not self.state.get('efficiency', {}).get('offline') and r.get('last_time') is not None else 0
        text = [f"{r['name']}｜{STAGES.get(r.get('degree'), '階段未同步')}｜Lv.{r.get('level')}",
                '進度 '+(f'{percent:.1f}%' if percent is not None else '待同步'),
                f"累積經驗 {r.get('exp')}｜本次 +{r['earned']}｜本場 +{r.get('last_gain')}"]
        factor = {'分': 1, '時': 60, '天': 1440, '秒': 1/60}[self.unit.text]
        for title, (rate, count) in zip(('總平均', '近10場', '近30場'), rates(r)):
            speed = f'{rate*factor:,.1f}' if rate is not None else '等待樣本'
            text += [f'{title}（{count} 場）：{speed}／{self.unit.text}',
                     '升級：'+forecast(remaining, rate, elapsed)+'｜一轉190：'+(forecast(reborn, rate, elapsed) if r.get('degree') == 1 else '—')]
        if r.get('level_inferred') or r.get('degree_inferred'): text.append('此夥伴／坐騎的等級或階段依經驗曲線推估')
        self.info.text = '\n\n'.join(text)+'\n\n預估採用已完成戰鬥的有效樣本；未同步時不推算。'
