"""Android-only reusable neon UI shell.

Use actual app state for status; mockup screenshots are never embedded as
noninteractive controls. This module contains no game/IPC business logic.
"""
from pathlib import Path

from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.graphics import Color, Rectangle

from android_app.theme import (
    ACCENT, BORDER, MUTED, SOFT, SURFACE, TEXT, surface, style_button,
)
from android_app.version import ANDROID_VERSION


class BrandHeader(BoxLayout):
    """Shared launcher/verification/workspace heading and genuine status."""

    def __init__(self, subtitle='', verified=False, **kwargs):
        super().__init__(orientation='horizontal', size_hint_y=None,
                         height=dp(108), spacing=dp(9),
                         padding=[dp(10), dp(9), dp(10), dp(9)], **kwargs)
        surface(self, color=SURFACE, radius=23, border=BORDER)
        # The same decorative castle artwork is shared by the login and
        # all 18 game workspaces, not just the verification gateway.
        with self.canvas.before:
            Color(1, 1, 1, .34)
            self._lala_castle_art = Rectangle(
                source=str(Path(__file__).resolve().parent /
                           'assets/verification_castle.jpg'))
        def art_geometry(*_):
            width = min(dp(166), self.width * .44)
            self._lala_castle_art.pos = (self.right - width - dp(2),
                                         self.y + dp(2))
            self._lala_castle_art.size = (width,
                                          max(0, self.height - dp(4)))
        self.bind(pos=art_geometry, size=art_geometry)
        art_geometry()
        logo = Image(
            source=str(Path(__file__).resolve().parent / 'assets/app.png'),
            size_hint_x=None, width=dp(68),
            fit_mode='contain',
        )
        self.add_widget(logo)

        labels = BoxLayout(orientation='vertical', spacing=dp(2))
        name = Label(text='飄流 RE:LaLa', color=ACCENT,
                     font_size='23sp', bold=True,
                     halign='left', valign='middle',
                     size_hint_y=None, height=dp(34))
        detail = Label(text='ANDROID  ·  v' + ANDROID_VERSION + ' / ' + subtitle,
                       color=MUTED, font_size='11sp',
                       halign='left', valign='middle',
                       size_hint_y=None, height=dp(21))
        self.status = Label(color=MUTED, font_size='11sp',
                            halign='left', valign='middle',
                            size_hint_y=None, height=dp(27))
        surface(self.status, color=(.017, .125, .21, .96),
                border=BORDER, radius=12)
        for item in (name, detail, self.status):
            item.bind(size=lambda w, size: setattr(
                w, 'text_size', (max(0, size[0]), size[1])))
            labels.add_widget(item)
        self.add_widget(labels)
        self.set_verified(verified)

    def set_verified(self, verified):
        # Do not paint a success state from a guessed or stale cache.
        verified = verified is True
        if getattr(self, '_verified', None) is verified:
            return
        self._verified = verified
        self.status.text = ('✓ 官方資源已驗證' if verified
                            else '○ 官方資源尚未通過驗證')
        self.status.color = ACCENT if verified else MUTED
        surface(self.status, color=(.018, .15, .22, .96),
                border=ACCENT if verified else BORDER, radius=12)


NAV_ROUTES = (
    ('首頁', '角色概況'),
    ('資料／資源', '包包與特技'),
    ('運行紀錄', '事件紀錄'),
    ('工具箱', 'AI與補給設定'),
)


# Every existing role function stays available in the 18-item selector.
# These groups only determine the highlighted bottom route.
PAGE_GROUPS = {
    '角色概況': '角色概況',
    '小地圖': '角色概況',
    '戰場陣形': '角色概況',
    '聊天': '角色概況',
    '組隊': '角色概況',
    '夥伴出戰': '角色概況',
    '遠征': '角色概況',
    '副本資料': '角色概況',
    '包包與特技': '包包與特技',
    '角色能力': '包包與特技',
    '煉金': '包包與特技',
    '製作': '包包與特技',
    'NPC': '包包與特技',
    '儲藏存取': '包包與特技',
    '事件紀錄': '事件紀錄',
    '經驗效率': '事件紀錄',
    'AI與補給設定': 'AI與補給設定',
    '福利': 'AI與補給設定',
}


class NavigationDock(BoxLayout):
    """Four real, accessible routes to existing Android feature pages."""

    def __init__(self, navigate, **kwargs):
        super().__init__(orientation='horizontal',
                         size_hint_y=None, height=dp(64),
                         spacing=dp(4), padding=[dp(5), dp(5)], **kwargs)
        surface(self, color=SURFACE, radius=19, border=BORDER)
        self.buttons = {}
        symbols = ('⌂', '◇', '☷', '⚙')
        for i, (title, page) in enumerate(NAV_ROUTES):
            view = style_button(Button(
                text=symbols[i] + '\\n' + title, size_hint_y=None,
                height=dp(54)), radius=16)
            # Two lines leave touch labels legible on 320dp phones.
            view.font_size = '11sp'
            view.bind(on_release=lambda _button, target=page: navigate(target))
            self.buttons[page] = view
            self.add_widget(view)
        self.set_active(NAV_ROUTES[0][1])

    def set_active(self, page):
        selected = PAGE_GROUPS.get(page, page)
        for route, button in self.buttons.items():
            style_button(button, primary=route == selected, radius=16)
            button.font_size = '11sp'


def section_title(title, subtitle=''):
    """Shared neon heading for every existing Android feature page."""
    block = BoxLayout(orientation='vertical', size_hint_y=None,
                      height=dp(49 if subtitle else 36),
                      spacing=dp(2))
    top = BoxLayout(orientation='horizontal', size_hint_y=None,
                    height=dp(34), spacing=dp(3))
    mark = Label(text='◇', color=ACCENT, font_size='23sp',
                 size_hint_x=None, width=dp(29))
    top.add_widget(mark)
    name = Label(text=title, color=TEXT, font_size='18sp',
                 bold=True, halign='left', valign='middle')
    name.bind(size=lambda w, size: setattr(
        w, 'text_size', (max(0, size[0]), size[1])))
    top.add_widget(name)
    block.add_widget(top)
    if subtitle:
        info = Label(text=subtitle, color=MUTED, font_size='12sp',
                     halign='left', valign='middle')
        info.bind(size=lambda w, size: setattr(
            w, 'text_size', (max(0, size[0]), size[1])))
        block.add_widget(info)
    return block
