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

from android_app.theme import (
    ACCENT, BORDER, MUTED, SOFT, SURFACE, TEXT, surface, style_button,
)
from android_app.version import ANDROID_VERSION


class BrandHeader(BoxLayout):
    """Shared launcher/verification/workspace heading and genuine status."""

    def __init__(self, subtitle='', verified=False, **kwargs):
        super().__init__(orientation='horizontal', size_hint_y=None,
                         height=dp(100), spacing=dp(10),
                         padding=[dp(12), dp(9), dp(12), dp(9)], **kwargs)
        surface(self, color=SURFACE, radius=23, border=BORDER)
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
        self.status = Label(color=MUTED, font_size='12sp',
                            halign='left', valign='middle',
                            size_hint_y=None, height=dp(22))
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
        self.status.text = ('● 官方資源已驗證' if verified
                            else '○ 官方資源尚未通過驗證')
        self.status.color = ACCENT if verified else MUTED


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
        for title, page in NAV_ROUTES:
            view = style_button(Button(text=title, size_hint_y=None,
                                       height=dp(54)), radius=16)
            # Long Chinese labels must fit a 320dp phone with four columns.
            view.font_size = '12sp'
            view.bind(on_release=lambda _button, target=page: navigate(target))
            self.buttons[page] = view
            self.add_widget(view)
        self.set_active(NAV_ROUTES[0][1])

    def set_active(self, page):
        selected = PAGE_GROUPS.get(page, page)
        for route, button in self.buttons.items():
            style_button(button, primary=route == selected, radius=16)
            button.font_size = '12sp'


def section_title(title, subtitle=''):
    """A self-sized heading for cards; safe on narrow Android devices."""
    block = BoxLayout(orientation='vertical', size_hint_y=None,
                      height=dp(47 if subtitle else 36),
                      spacing=dp(1))
    name = Label(text=title, color=TEXT, font_size='19sp',
                 bold=True, halign='left', valign='middle')
    name.bind(size=lambda w, size: setattr(w, 'text_size', size))
    block.add_widget(name)
    if subtitle:
        info = Label(text=subtitle, color=MUTED, font_size='12sp',
                     halign='left', valign='middle')
        info.bind(size=lambda w, size: setattr(w, 'text_size', size))
        block.add_widget(info)
    return block
