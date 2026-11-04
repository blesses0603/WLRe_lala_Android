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
from kivy.core.image import Image as CoreImage
from kivy.graphics import Color, Ellipse, Line, Rectangle

from android_app.theme import (
    ACCENT, BORDER, MUTED, SOFT, SURFACE, TEXT, surface, neon_surface,
    style_button,
)
from android_app.version import ANDROID_VERSION


class BrandHeader(BoxLayout):
    """Shared real-data mascot/sky header used by login and all workspaces."""

    def __init__(self, subtitle='', verified=False, **kwargs):
        super().__init__(orientation='horizontal', size_hint_y=None,
                         height=dp(112), spacing=dp(9),
                         padding=[dp(10), dp(9), dp(10), dp(9)], **kwargs)
        neon_surface(self, color=SURFACE, radius=24, border=BORDER, bright=True)

        assets = Path(__file__).resolve().parent / 'assets'
        castle = assets / 'verification_castle.jpg'
        self._castle_texture = None
        if castle.is_file():
            try:
                self._castle_texture = CoreImage(str(castle)).texture
            except Exception:
                # Decorative JPEGs are optional: Kivy SDL2 raises a generic
                # Exception for truncated/corrupt images. Never block login,
                # the resource gate, or other real UI controls for artwork.
                self._castle_texture = None
        with self.canvas.before:
            self._castle_tint = Color(.55, .85, 1, .25)
            self._castle_image = Rectangle(texture=self._castle_texture)
            Color(.18, .84, 1, .20)
            self._header_ring = Line(circle=(0, 0, 1), width=1)
            Color(.65, .94, 1, .64)
            self._header_stars = [Ellipse() for _ in range(6)]
        self.bind(pos=self._paint_sky, size=self._paint_sky)
        self._paint_sky()

        portrait = assets / 'verification_mascot.jpg'
        if portrait.is_file():
            try:
                # CoreImage surfaces decode failures before this asset is
                # mounted as a live Kivy Image. A corrupt decoration must
                # never hide the login and resource verification controls.
                CoreImage(str(portrait)).texture
            except Exception:
                portrait = assets / 'app.png'
        else:
            portrait = assets / 'app.png'
        self.logo = Image(source=str(portrait),
                          size_hint_x=None, width=dp(87),
                          fit_mode='contain')
        self.add_widget(self.logo)

        labels = BoxLayout(orientation='vertical', spacing=dp(3))
        name = Label(text='飄流 RE:LaLa', color=ACCENT,
                     font_size='22sp', bold=True,
                     halign='left', valign='middle',
                     size_hint_y=None, height=dp(36))
        detail = Label(text='ANDROID  ·  v' + ANDROID_VERSION + ' / ' + subtitle,
                       color=MUTED, font_size='11sp',
                       halign='left', valign='middle',
                       size_hint_y=None, height=dp(23))
        self.status = Label(color=MUTED, font_size='11sp',
                            halign='left', valign='middle',
                            size_hint_y=None, height=dp(26))
        neon_surface(self.status, color=(.03, .20, .27, .96),
                     radius=12, border=(.18,.73,.86,.50))
        for item in (name, detail, self.status):
            item.bind(size=lambda w, size: setattr(
                w, 'text_size', (max(0, size[0]-dp(6)), size[1])))
            labels.add_widget(item)
        self.add_widget(labels)
        self.set_verified(verified)

    def _paint_sky(self, *_):
        x, y, width, height = self.x, self.y, self.width, self.height
        if self._castle_texture is not None:
            self._castle_image.pos = (x+width*.63, y+dp(3))
            self._castle_image.size = (width*.37, height-dp(6))
        else:
            self._castle_image.size = (0, 0)
        self._header_ring.circle = (x+width*.84, y+height*.57, dp(42))
        for mark, (px,py) in zip(
                self._header_stars,
                ((.08,.86),(.28,.95),(.53,.79),(.71,.91),(.90,.82),(.95,.30))):
            mark.pos = (x+width*px, y+height*py)
            mark.size = (dp(2),dp(2))

    def set_verified(self, verified):
        # Never infer a successful source check from an asset or offline value.
        verified = verified is True
        if getattr(self, '_verified', None) is verified:
            return
        self._verified = verified
        self.status.text = ('✓ 官方資源已驗證' if verified
                            else '○ 官方資源尚未通過驗證')
        self.status.color = ACCENT if verified else MUTED


NAV_ROUTES = (
    ('首頁', '角色概況'),
    ('資料／資源', '包包與特技'),
    ('運行紀錄', '事件紀錄'),
    ('工具箱', 'AI與補給設定'),
)


# The original 18 functions remain available beside three paired pages.
# These groups only determine the highlighted bottom route.
PAGE_GROUPS = {
    '角色概況': '角色概況',
    '小地圖': '角色概況',
    '戰場陣形': '角色概況',
    '聊天＋組隊': '角色概況',
    '遠征＋副本': '角色概況',
    '煉金＋製作': '包包與特技',
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
        neon_surface(self, color=SURFACE, radius=19, border=BORDER, bright=True)
        self.buttons = {}
        for title, page in NAV_ROUTES:
            symbol = ('⌂', '▦', '◷', '⚙')[len(self.buttons)]
            view = style_button(Button(text=symbol+'\n'+title, size_hint_y=None,
                                       height=dp(54)), radius=16)
            # Two-line icon labels fit narrow 320dp screens.
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


PAGE_SYMBOLS = {
    '角色概況':'◈','包包與特技':'▦','小地圖':'◇','戰場陣形':'✥',
    '聊天＋組隊':'✉','遠征＋副本':'✧','煉金＋製作':'⚒',
    '聊天':'✉','組隊':'♧','夥伴出戰':'♢','遠征':'✧',
    '副本資料':'◇','角色能力':'✦','煉金':'⬡','製作':'⚒',
    '經驗效率':'◴','事件紀錄':'▤','AI與補給設定':'⚙',
    'NPC':'♙','儲藏存取':'▣','福利':'✧',
}


def section_title(title, subtitle='', icon=None, *, show_icon=True):
    """Icon-and-text header shared by login, dialogs and feature cards."""
    block = BoxLayout(orientation='vertical', size_hint_y=None,
                      height=dp(52 if subtitle else 38), spacing=dp(2))
    line = BoxLayout(orientation='horizontal', size_hint_y=None,
                     height=dp(32), spacing=dp(7))
    icon_text = icon if icon is not None else PAGE_SYMBOLS.get(title, '✧')
    # On compact embedded screens omit unsupported Unicode fallback glyphs
    # rather than rendering missing-font square boxes.
    if show_icon:
        # Prefer bundled 1262 game artwork for all existing pages.
        from android_app.assets import function_icon
        sprite = function_icon(title, 28)
        if sprite is not None:
            sprite.size_hint_x = None
            sprite.width = dp(30)
            line.add_widget(sprite)
        else:
            symbol = Label(text=icon_text, color=ACCENT, font_size='22sp',
                           size_hint_x=None, width=dp(30))
            line.add_widget(symbol)
    name = Label(text=title, color=TEXT, font_size='18sp',
                 bold=True, halign='left', valign='middle')
    name.bind(size=lambda w, size: setattr(
        w, 'text_size', (max(0, size[0]), size[1])))
    line.add_widget(name)
    block.add_widget(line)
    if subtitle:
        info = Label(text=subtitle, color=MUTED, font_size='11sp',
                     halign='left', valign='middle',
                     size_hint_y=None, height=dp(18))
        info.bind(size=lambda w, size: setattr(
            w, 'text_size', (max(0, size[0]), size[1])))
        block.add_widget(info)
    return block
