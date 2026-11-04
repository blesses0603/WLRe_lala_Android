"""High-fidelity, touch-safe Android official verification gateway.

Reference-inspired castle header, seven independently reported checkpoints,
version cards, recent results and neon action buttons. All data is actual
service/Activity verification data. Static canvas glow never animates.
"""
from pathlib import Path

from kivy.graphics import Color, RoundedRectangle, InstructionGroup
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView

from android_app.theme import (
    ACCENT, BACKGROUND, BORDER, MUTED, SOFT, SURFACE, TEXT,
    surface, style_button,
)
from android_app.version import ANDROID_VERSION
from android_app.widgets import button
from android_app.verification_presenter import CHECKS

GREEN = (0.49, 0.99, 0.61, 1)
AMBER = (1.0, 0.82, 0.40, 1)
RED = (1.0, 0.52, 0.59, 1)
DARK_CARD = (0.025, 0.090, 0.167, 0.99)
DARK_INNER = (0.040, 0.146, 0.250, 0.98)
ASSETS = Path(__file__).resolve().parent / 'assets'


def _label(value, size='14sp', *, color=TEXT, bold=False,
           height=33, horizontal='left', grow=False):
    view = Label(text=value, color=color, font_size=size, bold=bold,
                 size_hint_y=None, height=dp(height),
                 halign=horizontal, valign='middle')
    view.bind(width=lambda w, _: setattr(
        w, 'text_size', (max(0, w.width - dp(4)), None)))
    if grow:
        view.bind(texture_size=lambda w, _: setattr(
            w, 'height', max(dp(height), w.texture_size[1] + dp(10))))
    return view


def _card(title=None, subtitle='', *, highlighted=False):
    panel = BoxLayout(orientation='vertical', size_hint_y=None,
                      spacing=dp(7),
                      padding=[dp(11), dp(10), dp(11), dp(11)])
    panel.bind(minimum_height=panel.setter('height'))
    _glow(panel, strong=highlighted)
    if title:
        heading = _label(title, '18sp', bold=True, height=30)
        panel.add_widget(heading)
        if subtitle:
            panel.add_widget(_label(subtitle, '12sp',
                                   color=MUTED, height=24, grow=True))
    return panel


def _glow(view, *, strong=False):
    """Static 2-layer halo, not an animated blur/shader."""
    group = InstructionGroup()
    tint = Color(ACCENT[0], ACCENT[1], ACCENT[2],
                 0.15 if strong else 0.055)
    halo = RoundedRectangle(radius=[dp(24)])
    group.add(tint)
    group.add(halo)
    view.canvas.before.add(group)
    surface(view, color=DARK_CARD if strong else SURFACE,
            border=ACCENT if strong else BORDER, radius=20)

    def resize(*_):
        outer = dp(3 if strong else 2)
        halo.pos = (view.x - outer, view.y - outer)
        halo.size = (view.width + 2 * outer, view.height + 2 * outer)
    resize()
    view.bind(pos=resize, size=resize)


def _neon_primary(view):
    group = InstructionGroup()
    glow = Color(ACCENT[0], ACCENT[1], ACCENT[2], .21)
    halo = RoundedRectangle(radius=[dp(25)])
    group.add(glow)
    group.add(halo)
    # The halo must be behind the actual interactive Button's background.
    view.canvas.before.insert(0, group)
    def resize(*_):
        halo.pos = (view.x - dp(3), view.y - dp(3))
        halo.size = (view.width + dp(6), view.height + dp(6))
    view.bind(pos=resize, size=resize)
    resize()
    style_button(view, primary=True, radius=23)
    return view


class VerificationHero(FloatLayout):
    """Header uses the app mascot plus the user's *decorative* castle crop."""

    def __init__(self, **kwargs):
        super().__init__(size_hint_y=None, height=dp(110), **kwargs)
        _glow(self)
        art = Image(source=str(ASSETS / 'verification_castle.jpg'),
                    size_hint=(.57, 1), pos_hint={'right': 1, 'top': 1},
                    fit_mode='cover', opacity=.88)
        self.add_widget(art)
        mascot = Image(source=str(ASSETS / 'app.png'),
                       size_hint=(None, None),
                       size=(dp(84), dp(93)),
                       pos_hint={'x': .012, 'center_y': .51},
                       fit_mode='contain')
        self.add_widget(mascot)

        self.heading = _label('飄流 RE:LaLa', '22sp',
                              color=ACCENT, bold=True, height=34)
        self.subtitle = _label(
            'ANDROID  ·  v' + ANDROID_VERSION + ' / 資源驗證',
            '11sp', color=TEXT, height=25)
        self.status = _label('○ 官方資源尚未通過驗證',
                             '11sp', color=MUTED, height=26)
        self._verified = None
        self._state = None
        self.info_box = BoxLayout(
            orientation='vertical', size_hint=(None, None),
            spacing=dp(1), height=dp(91))
        self.info_box.add_widget(self.heading)
        self.info_box.add_widget(self.subtitle)
        surface(self.status, color=(0.016, .16, .24, .91),
                border=BORDER, radius=16)
        self.info_box.add_widget(self.status)
        self.add_widget(self.info_box)

        def arrange(*_):
            self.info_box.pos = (self.x + dp(91), self.y + dp(12))
            self.info_box.width = max(dp(115), self.width - dp(101))
        self.bind(pos=arrange, size=arrange)
        arrange()

    def set_verified(self, verified):
        verified = verified is True
        if self._verified == verified:
            return
        self._verified = verified
        self.set_state('success' if verified else 'waiting')

    def set_state(self, state):
        if self._state == state:
            return
        self._state = state
        states = {
            'success': ('✓ 官方資源驗證完成', GREEN),
            'checking': ('◉ 官方資源驗證中', ACCENT),
            'error': ('! 官方資源尚未通過驗證', RED),
            'waiting': ('○ 官方資源尚未通過驗證', MUTED),
        }
        message, tint = states.get(state, states['waiting'])
        self.status.text = message
        self.status.color = tint
        surface(self.status,
                color=(.025, .17, .25, .96) if state == 'success'
                      else (.018, .13, .22, .94),
                border=tint, radius=16)


class VerificationStep(BoxLayout):
    """A real, status-driven row; unlike the former fixed three labels."""

    STATUSES = {
        'waiting': ('待檢查', MUTED, '○'),
        'checking': ('檢查中', ACCENT, '◉'),
        'success': ('驗證成功', GREEN, '✓'),
        'error': ('未通過', RED, '!'),
    }

    def __init__(self, index, title, description, **kwargs):
        super().__init__(orientation='horizontal', size_hint_y=None,
                         height=dp(56), spacing=dp(7),
                         padding=[dp(7), dp(2), dp(7), dp(2)], **kwargs)
        surface(self, color=DARK_INNER, radius=14)
        self.index = _label(str(index), '14sp', color=ACCENT, bold=True,
                            height=44, horizontal='center')
        self.index.size_hint_x = None
        self.index.width = dp(33)
        surface(self.index, color=(.032, .20, .29, .96),
                border=BORDER, radius=14)
        self.add_widget(self.index)
        details = BoxLayout(orientation='vertical', spacing=dp(1))
        self.add_widget(details)
        details.add_widget(_label(title, '14sp', bold=True,
                                  height=dp(23)))
        details.add_widget(_label(description, '11sp', color=MUTED,
                                  height=26))
        self.result = _label('待檢查', '12sp', color=MUTED,
                             height=44, horizontal='center')
        self.result.size_hint_x = None
        self.result.width = dp(77)
        self.add_widget(self.result)
        self.current = None
        self.set_status('waiting')

    def set_status(self, status):
        status = status if status in self.STATUSES else 'waiting'
        if status == self.current:
            return
        self.current = status
        word, color, glyph = self.STATUSES[status]
        self.result.text = glyph + ' ' + word
        self.result.color = color
        self.index.color = color
        surface(self.index, color=(.03, .15, .24, .98),
                border=color, radius=14)
        surface(self, color=DARK_INNER,
                border=color if status in ('checking', 'error') else BORDER,
                radius=14)


class VerificationScreen(ScrollView):
    """One scrollable Android gateway; no decorative buttons without actions."""

    def __init__(self, retry, restart, **kwargs):
        super().__init__(do_scroll_x=False, bar_width=dp(3), **kwargs)
        self.content = BoxLayout(orientation='vertical', size_hint_y=None,
                                 spacing=dp(9),
                                 padding=[dp(10), dp(10), dp(10), dp(20)])
        self.content.bind(minimum_height=self.content.setter('height'))
        self.add_widget(self.content)

        self.header = VerificationHero()
        self.content.add_widget(self.header)

        checkpoints = _card('▱  官方資料與資料庫檢查',
                            '啟動前驗證 · 官方版本／資源完整性／Runtime')
        checkpoints.add_widget(_label(
            '首次啟動必須核對官方版本、雙 Manifest、必要 Bundle、'
            '完整 Runtime 與 SQLite 資料庫；全部通過才會進入登入。',
            '13sp', height=58, grow=True))
        self.steps = []
        for index, (_, name, detail) in enumerate(CHECKS, 1):
            row = VerificationStep(index, name, detail)
            self.steps.append(row)
            checkpoints.add_widget(row)
        self.content.add_widget(checkpoints)

        versions = _card('ⓘ  版本資訊')
        version_row = BoxLayout(orientation='horizontal', size_hint_y=None,
                                height=dp(58), spacing=dp(8))
        self.version_values = {}
        for name in ('DataPackage', 'MainPackage'):
            item = BoxLayout(orientation='vertical', size_hint_y=None,
                             height=dp(55), padding=[dp(8), dp(4)],
                             spacing=dp(1))
            surface(item, color=DARK_INNER, radius=13)
            item.add_widget(_label(name, '11sp', color=MUTED, height=22))
            value = _label('—', '17sp', color=TEXT, bold=True, height=28)
            item.add_widget(value)
            self.version_values[name] = value
            version_row.add_widget(item)
        versions.add_widget(version_row)
        versions.add_widget(_label(
            '檢查來源：官方伺服器　·　驗證模式：啟動檢查',
            '11sp', color=MUTED, height=27, grow=True))
        self.content.add_widget(versions)

        results = _card('⌁  最近檢查結果', highlighted=True)
        self.status = _label('等待背景服務與資源驗證',
                             '16sp', color=AMBER, bold=True, height=33,
                             grow=True)
        results.add_widget(self.status)
        self.detail = _label('等待官方檢查結果',
                             '13sp', color=TEXT, height=44, grow=True)
        results.add_widget(self.detail)
        self.checked_at = _label('檢查時間：尚無紀錄',
                                 '11sp', color=MUTED, height=23)
        results.add_widget(self.checked_at)
        self.content.add_widget(results)

        self.retry = _neon_primary(
            button('⟳  重新檢查官方資料  »', retry, 56))
        self.content.add_widget(self.retry)
        self.restart = button(
            '▷  啟動／重新連接背景服務', restart, 52)
        self.content.add_widget(self.restart)
        footer = _label(
            'ⓘ  若官方資源校驗失敗，請查看原因後重新檢查；'
            '不會跳過任何驗證。',
            '11sp', color=MUTED, height=44, grow=True)
        self.content.add_widget(footer)
        self._last_signature = None

    def render(self, model):
        signature = (
            model['steps'], model['overall'], model['headline'],
            model['detail'], tuple(sorted(model['versions'].items())),
            model['checked_at'],
        )
        if signature == self._last_signature:
            return
        self._last_signature = signature
        self.header.set_state(model['overall'])
        for widget, status in zip(self.steps, model['steps']):
            widget.set_status(status)
        for name, view in self.version_values.items():
            value = model['versions'].get(name, '—')
            if view.text != value:
                view.text = value
        self.status.text = model['headline']
        self.status.color = {
            'success': GREEN, 'checking': ACCENT,
            'error': RED, 'waiting': AMBER,
        }[model['overall']]
        self.detail.text = model['detail']
        self.checked_at.text = '檢查時間：' + model['checked_at']
