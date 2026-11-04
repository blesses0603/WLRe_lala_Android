"""High-fidelity, Android-only live verification screen.

The user-provided design is a VISUAL reference, not a source of game state.
All seven markers remain pending until independently confirmed by the
existing service and Activity validation gates. No continuous animations.
"""
from pathlib import Path

from kivy.graphics import Color, Ellipse, Line, Rectangle, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView

from android_app.theme import ACCENT, MUTED, SURFACE, TEXT
from android_app.version import ANDROID_VERSION
from android_app.verification_presentation import STEPS, view_state

_SKY = (0.013, 0.044, 0.095, 1)
_PANEL = (0.025, 0.110, 0.195, 1)
_INNER = (0.032, 0.150, 0.246, 1)
_CYAN = (0.25, 0.91, 0.98, 1)
_GREEN = (0.45, 0.94, 0.61, 1)
_RED = (1.0, 0.57, 0.57, 1)
_DARK = (0.40, 0.62, 0.75, 1)
_ASSETS = Path(__file__).resolve().parent / 'assets'


def txt(value, *, size='14sp', color=TEXT, height=29, bold=False):
    view = Label(text=value, color=color, font_size=size, bold=bold,
                 halign='left', valign='middle', size_hint_y=None,
                 height=dp(height))
    view.bind(width=lambda w, width: setattr(
        w, 'text_size', (max(0, width-dp(2)), None)))
    return view


def grow(view, minimum=24):
    """Grow a multiline label with real rendered content on small phones."""
    view.bind(texture_size=lambda w, size: setattr(
        w, 'height', max(dp(minimum), size[1] + dp(6))))
    return view


def glow_panel(view, *, fill=_PANEL, radius=20, bright=False):
    """Static multi-layer cyan border; no shaders or animation timers."""
    with view.canvas.before:
        halo = Color(.05, .78, 1, .25 if bright else .11)
        outer = RoundedRectangle(radius=[dp(radius+3)])
        edge = Color(.16, .82, 1, .88 if bright else .54)
        rim = RoundedRectangle(radius=[dp(radius)])
        inside = Color(*fill)
        face = RoundedRectangle(radius=[dp(radius-1)])
        shine = Color(.41, .96, 1, .37 if bright else .19)
        top = RoundedRectangle(radius=[dp(2)])

    def geometry(*_):
        x, y, width, height = view.x, view.y, view.width, view.height
        outer.pos = (x-dp(2), y-dp(2))
        outer.size = (width+dp(4), height+dp(4))
        rim.pos, rim.size = (x, y), (width, height)
        face.pos = (x+dp(1), y+dp(1))
        face.size = (max(0,width-dp(2)), max(0,height-dp(2)))
        top.pos = (x+dp(15), y+height-dp(2))
        top.size = (max(0,width-dp(30)), dp(1))
    geometry()
    view.bind(pos=geometry, size=geometry)
    view._lala_neon_art = (halo, outer, edge, rim, inside, face, shine, top)
    return view


class NeonAction(Button):
    def __init__(self, title, callback, *, primary=False, **kwargs):
        super().__init__(text=title, size_hint_y=None, height=dp(55),
                         font_size='17sp' if primary else '15sp',
                         bold=primary, **kwargs)
        self.background_normal = self.background_down = ''
        self.background_disabled_normal = ''
        self.background_color = (0,0,0,0)
        self.halign = 'center'
        self.valign = 'middle'
        self.bind(size=lambda w,size: setattr(
            w, 'text_size', (max(0,size[0]-dp(20)),size[1])))
        self._primary = primary
        glow_panel(self, fill=(_INNER if not primary else
                               (.015, .44, .56, 1)),
                   radius=29, bright=primary)
        self.bind(on_release=lambda *_:callback())
        self.bind(disabled=self._update_visual,
                  state=self._update_visual)
        self._update_visual()

    def _update_visual(self, *_):
        halo, outer, edge, rim, inside, face, shine, top = self._lala_neon_art
        if self.disabled:
            halo.rgba = (.1,.24,.34,.05)
            edge.rgba = (.18,.30,.40,.34)
            inside.rgba = (.055,.11,.17,.96)
            self.color = MUTED
        else:
            halo.rgba = (.08,.88,1,.34 if self._primary else .12)
            edge.rgba = (.30,.96,1,.96 if self._primary else .65)
            inside.rgba = ((.01,.32,.43,1) if self.state == 'down'
                           else (.015,.44,.56,1) if self._primary else _INNER)
            self.color = TEXT


class CosmicHeader(FloatLayout):
    """Decorative sky plus an actual mascot asset and true status badge."""

    def __init__(self, **kwargs):
        super().__init__(size_hint_y=None, height=dp(128), **kwargs)
        with self.canvas.before:
            Color(*_SKY)
            self.back = RoundedRectangle(radius=[dp(27)])
            self.ring_colors = []
            self.rings = []
            for index in range(4):
                self.ring_colors.append(Color(.12,.62,1,.25-index*.045))
                self.rings.append(Line(circle=(0,0,1),width=1))
            Color(.14,.63,.86,.13)
            self.mist = Ellipse()
            Color(.2,.9,1,.72)
            self.stars = [Ellipse() for _ in range(8)]
        self.bind(pos=self._geometry, size=self._geometry)

        castle = _ASSETS / 'verification_castle.jpg'
        if castle.is_file():
            self.castle = Image(source=str(castle), opacity=.60,
                size_hint=(None,None), size=(dp(125),dp(109)),
                pos_hint={'right':.99,'top':.99},fit_mode='contain')
            self.add_widget(self.castle)
        mascot = _ASSETS / 'verification_mascot.jpg'
        if not mascot.is_file():
            mascot = _ASSETS / 'app.png'
        self.add_widget(Image(source=str(mascot),fit_mode='contain',
            size_hint=(None,None),size=(dp(113),dp(119)),
            pos_hint={'x':.0,'center_y':.51}))
        headline = txt('飄流 RE:LaLa',size='23sp',
                       color=_CYAN,height=39,bold=True)
        headline.size_hint=(.65,None)
        headline.pos_hint={'x':.32,'top':.83}
        self.add_widget(headline)
        subtitle = txt('ANDROID  ·  v'+ANDROID_VERSION+' / 資源驗證',
                       size='11sp',color=MUTED,height=27)
        subtitle.size_hint=(.64,None)
        subtitle.pos_hint={'x':.32,'top':.56}
        self.add_widget(subtitle)

        self.badge = txt('◌ 官方資源尚未通過驗證',
                         size='12sp',color=_CYAN,height=32)
        self.badge.size_hint=(.62,None)
        self.badge.pos_hint={'x':.32,'top':.35}
        glow_panel(self.badge,fill=(.025,.22,.28,.92),radius=15)
        self.add_widget(self.badge)
        self._verified = None
        self.set_verified(False)
        self._geometry()

    def _geometry(self, *_):
        self.back.pos,self.back.size=self.pos,self.size
        cx = self.x + self.width*.77
        cy = self.y + self.height*.60
        for index, ring in enumerate(self.rings):
            ring.circle=(cx,cy,dp(30+17*index))
        self.mist.pos=(cx-dp(90),cy-dp(46))
        self.mist.size=(dp(180),dp(94))
        for i, star in enumerate(self.stars):
            px=(.10,.23,.43,.52,.68,.82,.89,.95)[i]
            py=(.88,.72,.95,.24,.86,.39,.91,.16)[i]
            star.pos=(self.x+self.width*px,self.y+self.height*py)
            star.size=(dp(2),dp(2))

    def set_verified(self, verified):
        verified = verified is True
        if self._verified is verified:
            return
        self._verified = verified
        self.badge.text = ('✓ 官方資源驗證已完成' if verified
                           else '◌ 官方資源尚未通過驗證')
        self.badge.color = _GREEN if verified else _CYAN


class CheckRow(BoxLayout):
    _COLORS = {
        'pending': (MUTED, '○', '未確認'),
        'checking': (_CYAN, '◉', '檢查中'),
        'passed': (_GREEN, '✓', '驗證成功'),
        'blocked': (_RED, '!', '未通過'),
    }

    def __init__(self, key, title, description, symbol, **kwargs):
        super().__init__(orientation='horizontal', size_hint_y=None,
                         height=dp(54), spacing=dp(6),
                         padding=[dp(8),dp(5),dp(8),dp(5)],**kwargs)
        glow_panel(self, fill=_INNER, radius=15)
        self.mark = Label(text=symbol, color=_CYAN, font_size='22sp',
                          size_hint_x=None,width=dp(34))
        self.add_widget(self.mark)
        descriptions = BoxLayout(orientation='vertical',spacing=dp(1))
        descriptions.add_widget(txt(title,size='15sp',height=24,bold=True))
        descriptions.add_widget(txt(description,size='10sp',
                                    height=18,color=MUTED))
        self.add_widget(descriptions)
        self.state = txt('',size='11sp',height=36,color=MUTED,bold=True)
        self.state.size_hint_x=None
        self.state.width=dp(80)
        self.state.halign='right'
        self.add_widget(self.state)
        self.key=key
        self._current=None
        self.update('pending')

    def update(self, kind):
        if kind == self._current:
            return
        self._current=kind
        color,mark,text=self._COLORS.get(kind,self._COLORS['pending'])
        self.state.text=mark+' '+text
        self.state.color=color
        self.mark.color=color


class VerificationDashboard(BoxLayout):
    """One vertically scrollable, real-data replacement for the plain gate."""

    _ICONS=('◇','▤','▱','≡','⬡','⚙','▣')

    def __init__(self, retry, start_service, **kwargs):
        super().__init__(orientation='vertical',**kwargs)
        self.scroller=ScrollView(do_scroll_x=False,bar_width=dp(3))
        root=BoxLayout(orientation='vertical',size_hint_y=None,
                       padding=[dp(12),dp(24),dp(12),dp(20)],
                       spacing=dp(9))
        root.bind(minimum_height=root.setter('height'))

        self.hero=CosmicHeader()
        root.add_widget(self.hero)

        inspection=BoxLayout(orientation='vertical',size_hint_y=None,
                             padding=[dp(11),dp(9),dp(11),dp(10)],
                             spacing=dp(4))
        inspection.bind(minimum_height=inspection.setter('height'))
        glow_panel(inspection,radius=24,bright=True)
        title=txt('⬡  官方資料與資料庫檢查',
                  size='21sp',height=38,bold=True)
        inspection.add_widget(title)
        self.caption=grow(txt(
            '首次啟動會核對官方版本、雙 Manifest、必要 Bundle、'
            '完整 Runtime 與 SQLite 資料庫。只有全部通過才開放帳號登入。',
            size='13sp',height=50),minimum=50)
        inspection.add_widget(self.caption)

        self.rows={}
        for (key,name,description),symbol in zip(STEPS,self._ICONS):
            item=CheckRow(key,name,description,symbol)
            inspection.add_widget(item)
            self.rows[key]=item
        root.add_widget(inspection)

        versions=BoxLayout(orientation='vertical',size_hint_y=None,
                           padding=[dp(12),dp(8),dp(12),dp(8)],
                           spacing=dp(7))
        versions.bind(minimum_height=versions.setter('height'))
        glow_panel(versions,radius=21)
        versions.add_widget(txt('ⓘ  版本資訊',size='18sp',
                                 height=32,bold=True))
        cards=BoxLayout(size_hint_y=None,height=dp(48),spacing=dp(8))
        self.version_labels={}
        for name in ('DataPackage','MainPackage'):
            card=BoxLayout(orientation='vertical',size_hint_y=None,
                           height=dp(48),padding=[dp(8),dp(3)])
            glow_panel(card,fill=_INNER,radius=13)
            card.add_widget(txt(name,size='11sp',height=19,color=MUTED))
            value=txt('— 尚未取得',size='14sp',color=_CYAN,
                      height=23,bold=True)
            card.add_widget(value)
            self.version_labels[name]=value
            cards.add_widget(card)
        versions.add_widget(cards)
        versions.add_widget(txt(
            '應用程式版本：v'+ANDROID_VERSION+'  ·  資料來源：官方伺服器',
            size='11sp',color=MUTED,height=21))
        root.add_widget(versions)

        result=BoxLayout(orientation='vertical',size_hint_y=None,
                         padding=[dp(12),dp(9),dp(12),dp(9)],
                         spacing=dp(4))
        result.bind(minimum_height=result.setter('height'))
        glow_panel(result,radius=21)
        result.add_widget(txt('⌁  最近檢查結果',
                               size='18sp',height=31,bold=True))
        self.status=txt('等待背景服務啟動',size='14sp',
                        color=_CYAN,height=29,bold=True)
        result.add_widget(self.status)
        self.detail=grow(txt('尚無檢查結果。',size='12sp',
                             color=MUTED,height=33),minimum=33)
        result.add_widget(self.detail)
        self.checked=txt('檢查時間：尚未取得',
                         size='11sp',height=21,color=MUTED)
        result.add_widget(self.checked)
        root.add_widget(result)

        self.retry=NeonAction('⟳ 重新檢查官方資料  »',
                              retry,primary=True)
        root.add_widget(self.retry)
        self.service_button=NeonAction(
            '▷  啟動／重新連接背景服務',start_service)
        root.add_widget(self.service_button)
        notice=grow(txt(
            'ⓘ 官方資源校驗未完成時，不提供帳號登入，'
            '也不會略過任何驗證。',
            size='11sp',height=24,color=MUTED),minimum=24)
        root.add_widget(notice)
        self.scroller.add_widget(root)
        self.add_widget(self.scroller)
        self._last_render=None

    def apply_state(self, service, local, *, connected, detail,
                    login_ready=False):
        view=view_state(service,local,connected=connected,
                        login_ready=login_ready)
        # This detail is the already-sanitized, bounded status from app.py.
        detail=detail[:550] if type(detail) is str else '檢查資料暫時無法讀取'
        revision=(tuple(sorted(view['steps'].items())),
                  tuple(sorted(view['versions'].items())),
                  view['headline'],view['kind'],
                  view['checked_at_utc'],view['approved'],detail)
        if revision==self._last_render:
            return
        self._last_render=revision
        self.hero.set_verified(view['approved'])
        for key,step in self.rows.items():
            step.update(view['steps'][key])
        for name,label in self.version_labels.items():
            version=view['versions'].get(name)
            label.text=(version if version else '— 尚未取得')
        self.status.text=view['headline']
        self.status.color=(_GREEN if view['approved']
                           else _RED if view['kind']=='blocked' else _CYAN)
        self.detail.text=detail
        checked=view['checked_at_utc']
        self.checked.text=('檢查時間（UTC）：'+checked if checked
                           else '檢查時間：尚未取得')
