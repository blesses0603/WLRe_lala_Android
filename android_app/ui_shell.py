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

    def __init__(self, subtitle='', verified=False, alerts=None,
                 settings=None, **kwargs):
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
                     shorten=True,
                     size_hint_y=None, height=dp(36))
        detail = Label(text='ANDROID  ·  v' + ANDROID_VERSION + ' / ' + subtitle,
                       color=MUTED, font_size='11sp',
                       halign='left', valign='middle',
                       size_hint_y=None, height=dp(23))
        self.status = Label(color=MUTED, font_size='11sp',
                            halign='left', valign='middle',
                            size_hint_y=None, height=dp(26))
        self.name_label, self.detail_label = name, detail
        self.actions = None
        neon_surface(self.status, color=(.03, .20, .27, .96),
                     radius=12, border=(.18,.73,.86,.50))
        for item in (name, detail, self.status):
            item.bind(size=lambda w, size: setattr(
                w, 'text_size', (max(0, size[0]-dp(6)), size[1])))
            labels.add_widget(item)
        self.add_widget(labels)
        if callable(alerts) and callable(settings):
            # Two actual navigable actions, drawn as vectors on Android.
            from android_app.pages.social_visual import SocialButton
            actions = BoxLayout(orientation='horizontal', size_hint_x=None,
                                width=dp(78),spacing=dp(5))
            bell = SocialButton('',alerts,icon='bell',height=36,
                                font='10sp',pos_hint={'top':1})
            gear = SocialButton('',settings,icon='settings',height=36,
                                font='10sp',pos_hint={'top':1})
            actions.add_widget(bell)
            actions.add_widget(gear)
            self.add_widget(actions)
            self.actions = actions
        self.bind(width=self.adapt_layout)
        self.adapt_layout()
        self.set_verified(verified)

    def adapt_layout(self, *_):
        """Preserve readable labels and both actions on a 320dp phone.

        The reference's wide artwork must not squeeze the title between an
        87dp portrait and a fixed horizontal 78dp action strip.
        """
        narrow = self.width < dp(420)
        self.logo.width = dp(48 if narrow else 87)
        self.spacing = dp(6 if narrow else 9)
        self.name_label.font_size = '18sp' if narrow else '22sp'
        self.detail_label.font_size = '9sp' if narrow else '11sp'
        self.status.font_size = '10sp' if narrow else '11sp'
        if self.actions is not None:
            self.actions.orientation = 'vertical' if narrow else 'horizontal'
            self.actions.width = dp(36 if narrow else 78)

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
    ('工具箱', '設定與工具'),
)


# The original 18 functions remain available beside five paired pages.
# These groups only determine the highlighted bottom route.
PAGE_GROUPS = {
    '角色概況': '角色概況',
    '小地圖': '角色概況',
    '戰場陣形': '角色概況',
    '聊天＋組隊': '角色概況',
    '遠征＋副本': '角色概況',
    '煉金＋製作': '包包與特技',
    '夥伴＋能力': '角色概況',
    '設定與工具': '設定與工具',
    '聊天': '角色概況',
    '組隊': '角色概況',
    '夥伴出戰': '角色概況',
    '遠征': '角色概況',
    '副本資料': '角色概況',
    '包包與特技': '包包與特技',
    '角色能力': '包包與特技',
    '煉金': '包包與特技',
    '製作': '包包與特技',
    'NPC': '設定與工具',
    '儲藏存取': '設定與工具',
    '事件紀錄': '事件紀錄',
    '經驗效率': '事件紀錄',
    'AI與補給設定': '設定與工具',
    '福利': '設定與工具',
}


class NavigationDock(BoxLayout):
    """Four accessible bottom routes with non-overlapping labels and icons."""

    def __init__(self, navigate, **kwargs):
        super().__init__(orientation='horizontal',
                         size_hint_y=None, height=dp(60),
                         spacing=dp(4), padding=[dp(5), dp(5)], **kwargs)
        neon_surface(self, color=SURFACE, radius=19, border=BORDER, bright=True)
        from android_app.pages.social_visual import SocialIcon
        self.buttons = {}
        self.icons = {}
        self.labels = {}
        for index, (title, page) in enumerate(NAV_ROUTES):
            # Button is the only touch target; children are decoration only.
            view = style_button(Button(text='', size_hint_y=1), radius=14)
            view.font_size = '11sp'
            picture = SocialIcon(('home','layers','bars','grid')[index],
                                 tint=MUTED, edge=20)
            name = Label(text=title, font_size='10sp', color=MUTED,
                         size_hint=(None, None), halign='center',
                         valign='middle', shorten=True)
            name.text_size = (dp(80), dp(17))
            view.add_widget(picture)
            view.add_widget(name)
            def position_content(w, *_, icon=picture, caption=name):
                icon.center_x = w.center_x
                icon.y = w.top - icon.height - dp(5)
                caption.pos = (w.x + dp(2), w.y + dp(3))
                caption.size = (max(0, w.width-dp(4)), dp(17))
                caption.text_size = caption.size
            view.bind(pos=position_content, size=position_content)
            position_content(view)
            view.bind(on_release=lambda _button, target=page: navigate(target))
            self.buttons[page] = view
            self.icons[page] = picture
            self.labels[page] = name
            self.add_widget(view)
        self.set_active(NAV_ROUTES[0][1])

    def set_active(self, page):
        selected = PAGE_GROUPS.get(page, page)
        for route, button in self.buttons.items():
            style_button(button, primary=route == selected, radius=14)
            self.icons[route].colorize(ACCENT if route == selected else MUTED)
            self.labels[route].color = TEXT if route == selected else MUTED

PAGE_SYMBOLS = {
    '角色概況':'◈','包包與特技':'▦','小地圖':'◇','戰場陣形':'✥',
    '聊天＋組隊':'✉','遠征＋副本':'✧','煉金＋製作':'⚒',
    '夥伴＋能力':'♢','設定與工具':'⚙',
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
            from android_app.pages.social_visual import SocialIcon
            vector = {
                '聊天＋組隊':'users', '聊天':'chat',
                '聊天訊息':'chat', '發送訊息':'send',
                '組隊':'users', '組隊管理':'users',
                '附近玩家':'pin', '我的隊伍':'users',
                '待確認邀請／申請':'message',
                '角色概況':'home', '包包與特技':'layers',
                '夥伴＋能力':'users', '設定與工具':'settings',
                '事件紀錄':'list', '小地圖':'pin',
                'AI與補給設定':'settings','角色能力':'chart',
                '煉金':'sparkle','製作':'settings',
            }.get(title,'sparkle')
            line.add_widget(SocialIcon(vector,edge=28))
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
