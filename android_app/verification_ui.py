"""Android resource gate: responsive game-style UI, backed by the existing gate.

Artwork is decoration only. Status, versions and permission to enter login
come exclusively from verification_presentation.view_state. No network work or
preview fixtures are started here. Only a live checking image may animate.
"""
from pathlib import Path

from kivy.animation import Animation
from kivy.app import App
from kivy.graphics import Color, Ellipse, Line, Rectangle, RoundedRectangle, PushMatrix, PopMatrix, Rotate
from kivy.graphics.texture import Texture
from kivy.core.image import Image as CoreImage
from kivy.metrics import dp, Metrics
from kivy.properties import NumericProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.widget import Widget
from kivy.uix.popup import Popup
from kivy.uix.button import Button
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView

from android_app.theme import ACCENT, MUTED, TEXT
from android_app.version import ANDROID_VERSION
from android_app.verification_presentation import STEPS, view_state
from android_app.verification_icons import VerificationRail
from android_app.verification_icons import CYAN as ICON_CYAN, GREEN as ICON_GREEN
from android_app.verification_icons import RED as ICON_RED, DIM as ICON_DIM

_SKY = (.014, .035, .073, 1)
_PANEL = (.035, .13, .22, 1)
_INNER = (.045, .18, .28, 1)
_CYAN = (.29, .94, .98, 1)
_GREEN = (.48, .95, .67, 1)
_RED = (1, .58, .58, 1)
_ASSETS = Path(__file__).resolve().parent / 'assets'
_GRADIENTS = {}


def txt(value, *, size='14sp', color=TEXT, height=24, bold=False):
    view = Label(text=value, color=color, font_size=size, bold=bold,
                 halign='left', valign='middle', size_hint_y=None,
                 height=dp(height))
    view.bind(width=lambda w, width: setattr(
        w, 'text_size', (max(0, width-dp(2)), None)))
    return view


def grow(view, minimum=24):
    view.bind(texture_size=lambda w, size: setattr(
        w, 'height', max(dp(minimum), size[1]+dp(4))))
    return view


def _gradient(fill):
    """One cached 1x32 texture per colour; no per-frame shader or image work."""
    key = tuple(fill)
    if key not in _GRADIENTS:
        texture = Texture.create(size=(1, 32), colorfmt='rgba')
        pixels = bytearray()
        for index in range(32):
            light = .78 + index / 31 * .38
            pixels.extend(int(min(1, channel*light)*255) for channel in fill[:3])
            pixels.append(int(fill[3]*255))
        data = bytes(pixels)
        def reload_texture(target, payload=data):
            target.blit_buffer(payload, colorfmt='rgba', bufferfmt='ubyte')
        texture.add_reload_observer(reload_texture)
        reload_texture(texture)
        _GRADIENTS[key] = texture
    return _GRADIENTS[key]


def glow_panel(view, *, fill=_PANEL, radius=18, bright=False):
    with view.canvas.before:
        halo = Color(.05, .72, .91, .12 if bright else .045)
        outer = RoundedRectangle(radius=[dp(radius+3)])
        edge = Color(.24, .75, .90, .78 if bright else .34)
        rim = RoundedRectangle(radius=[dp(radius)])
        inside = Color(1, 1, 1, 1)
        face = RoundedRectangle(radius=[dp(radius-1)], texture=_gradient(fill))
        shine = Color(.57, .98, 1, .60 if bright else .20)
        top = RoundedRectangle(radius=[dp(2)])
    def geometry(*_):
        x, y, width, height = view.x, view.y, view.width, view.height
        outer.pos, outer.size = (x-dp(3),y-dp(3)), (width+dp(6),height+dp(6))
        rim.pos, rim.size = view.pos, view.size
        face.pos = (x+dp(1),y+dp(1))
        face.size = (max(0,width-dp(2)),max(0,height-dp(2)))
        top.pos, top.size = (x+dp(18),y+height-dp(1)), (max(0,width-dp(36)),dp(1))
    geometry()
    view.bind(pos=geometry, size=geometry)
    view._lala_neon_art = (halo, outer, edge, rim, inside, face, shine, top)
    return view


_REFERENCE = None
_ICON_REGIONS = {
    'cube': (128, 409, 43, 43),
    'database': (130, 478, 40, 43),
    'layers': (126, 547, 47, 44),
    'document': (130, 614, 44, 44),
    'bundle': (124, 681, 52, 47),
    'gear': (127, 748, 49, 47),
    'settings': (127, 748, 49, 47),
    'wifi': (127, 748, 49, 47),
    'info': (52, 953, 50, 50),
    'pulse': (48, 1096, 50, 48),
    'refresh': (264, 1340, 54, 55),
    'play': (267, 1452, 48, 45),
    'check-circle': (750, 412, 34, 34),
    'shield': (239, 128, 28, 30),
    'error': (52, 953, 50, 50),
}


def _reference_region(region):
    """Sample unchanged pixels from the user's design, never its fake data.

    The PNG is a decorative atlas only. No screenshot is mounted as a UI
    background and no text, version, successful row or button is sampled.
    CoreImage retains the filename so Kivy can restore it after GL loss.
    """
    global _REFERENCE
    if _REFERENCE is None:
        try:
            _REFERENCE = CoreImage(str(_ASSETS / 'verification_reference.png'))
        except Exception:
            # Artwork is optional. A missing or corrupt image must never
            # prevent resource verification, retries or the login gate.
            _REFERENCE = False
    if _REFERENCE is False:
        return None
    x, y, width, height = region
    if x+width > _REFERENCE.width or y+height > _REFERENCE.height:
        return None
    return _REFERENCE.texture.get_region(x, _REFERENCE.height-y-height, width, height)


class ReferenceGlyph(Image):
    """Raster artwork from the supplied design, not Canvas/vector pictograms."""
    rotation_angle=NumericProperty(0)

    def __init__(self, icon, *, tint=None, edge=24, **kwargs):
        self.icon=icon
        self.tint=tint
        self._animation=None
        super().__init__(size_hint=(None,None),size=(dp(edge),dp(edge)),
                         fit_mode='contain',**kwargs)
        # Rotate the bitmap texture itself, never redraw a vector pictogram.
        with self.canvas.before:
            PushMatrix()
            self._rotation=Rotate(angle=0,origin=self.center)
        with self.canvas.after:
            PopMatrix()
        self.bind(rotation_angle=self._update_rotation,pos=self._update_rotation,size=self._update_rotation)
        self._paint()
    def set_animating(self,enabled):
        enabled=bool(enabled and self.texture is not None)
        if enabled and self._animation is None:
            self.rotation_angle=0
            self._animation=(Animation(rotation_angle=-360,duration=.9,t='linear')
                             + Animation(rotation_angle=0,duration=0))
            self._animation.repeat=True
            self._animation.start(self)
        elif not enabled and self._animation is not None:
            self._animation.cancel(self)
            self._animation=None
            self.rotation_angle=0
            self._paint()

    def _update_rotation(self,*_):
        self._rotation.angle=self.rotation_angle
        self._rotation.origin=self.center

    def set_tint(self,tint):
        self.tint=tint
        self._paint()
    def _paint(self,*_):
        region=_ICON_REGIONS.get(self.icon)
        if region is None:
            self.opacity=0
            return
        self.texture=_reference_region(region)
        self.opacity=0 if self.texture is None else .55 if self.tint==ICON_DIM else 1
        self.color=(1,.55,.55,1) if self.icon=='error' else (1,1,1,1)


class NeonAction(Button):
    """Touch-sized action with a separately reserved icon and text region."""
    def __init__(self, title, callback, *, primary=False, glyph=None, **kwargs):
        super().__init__(text='', size_hint_y=None, height=dp(46), **kwargs)
        self.background_normal = self.background_down = ''
        self.background_disabled_normal = ''
        self.background_color = (0,0,0,0)
        self._primary = primary
        self._compact_action=False
        glow_panel(self, fill=(.035,.145,.218,1), radius=20, bright=primary)
        self.glyph = ReferenceGlyph(glyph or ('refresh' if primary else 'play'), edge=21)
        self.caption = txt(title, size='14sp', height=24, bold=primary)
        self.caption.size_hint = (None,None)
        self.caption.halign = 'center'
        self.add_widget(self.glyph)
        self.add_widget(self.caption)
        self.bind(pos=self._place_icon, size=self._place_icon)
        self.bind(on_release=lambda *_: callback())
        self.bind(disabled=self._update_visual, state=self._update_visual)
        self._place_icon()
        self._update_visual()

    def compact_caption(self):
        self._compact_action=True
        self.glyph.size=(dp(16),dp(16))
        self.caption.font_size='12sp'
        self._place_icon()

    def _place_icon(self, *_):
        if self._compact_action:
            self.glyph.pos=(self.x+dp(12),self.center_y-self.glyph.height/2)
            self.caption.pos=(self.x+dp(36),self.y+dp(4))
            self.caption.size=(max(0,self.width-dp(44)),self.height-dp(8))
            self.caption.text_size=self.caption.size
            return
        self.glyph.pos = (self.x+dp(17),self.center_y-self.glyph.height/2)
        self.caption.pos = (self.x+dp(46),self.y+dp(4))
        self.caption.size = (max(0,self.width-dp(63)),self.height-dp(8))
        self.caption.text_size = self.caption.size

    def _update_visual(self, *_):
        halo, outer, edge, rim, inside, face, shine, top = self._lala_neon_art
        if self.disabled:
            halo.rgba = (.1,.2,.3,.025)
            edge.rgba = (.20,.35,.44,.28)
            face.texture = _gradient((.035,.085,.13,1))
            self.caption.color = (.40,.57,.65,1)
            self.glyph.set_tint(ICON_DIM)
        else:
            halo.rgba = (.04,.85,.95,.15 if self._primary else .04)
            edge.rgba = (.39,.96,1,.95 if self._primary else .42)
            fill = ((.015,.28,.36,1) if self.state == 'down' else
                    (.012,.45,.54,1) if self._primary else (.035,.145,.218,1))
            face.texture = _gradient(fill)
            self.caption.color = TEXT
            self.glyph.set_tint(ICON_CYAN)


class CosmicHeader(FloatLayout):
    """Original-design image scene with live text and status above it."""
    def __init__(self, **kwargs):
        super().__init__(size_hint_y=None, height=dp(105), **kwargs)
        art=_ASSETS / 'verification_header_art.png'
        try:
            self._scene_source=CoreImage(str(art)) if art.is_file() else None
        except Exception:
            self._scene_source=None
        crop_height=min(520,self._scene_source.height) if self._scene_source else 0
        scene_texture=(self._scene_source.texture.get_region(0,self._scene_source.height-crop_height,
                       self._scene_source.width,crop_height) if self._scene_source else None)
        self.scene=Image(texture=scene_texture,fit_mode='fill',size_hint=(1,1))
        self.add_widget(self.scene)
        # Temporary fallback is still raster artwork, never vector recreation.
        self.mascot=Image(texture=_reference_region((0,0,215,191)),fit_mode='contain',
                          size_hint=(None,None),opacity=0 if self._scene_source else 1)
        self.castle=Image(texture=_reference_region((535,0,240,190)),fit_mode='contain',
                          size_hint=(None,None),opacity=0 if self._scene_source else .8)
        self.add_widget(self.castle);self.add_widget(self.mascot)
        self.headline=txt('飄流 RE:LaLa',size='21sp',color=_CYAN,height=32,bold=True)
        self.subtitle=txt('ANDROID  ·  v'+ANDROID_VERSION,size='10sp',color=MUTED,height=18)
        self.badge=txt('官方資源尚未通過驗證',size='10sp',color=_CYAN,height=25)
        for view in (self.headline,self.subtitle,self.badge):
            view.size_hint=(None,None);self.add_widget(view)
        self._verified=None
        self.bind(pos=self._geometry,size=self._geometry)
        self.set_verified(False);self._geometry()
    def _geometry(self,*_):
        narrow=self.width<dp(340)
        left=self.x+self.width*.25
        available=self.width*.71
        self.scene.pos,self.scene.size=self.pos,self.size
        self.mascot.pos=(self.x,self.y); self.mascot.size=(self.width*.24,self.height)
        self.castle.pos=(self.x+self.width*.56,self.y);self.castle.size=(self.width*.44,self.height)
        if self.height<dp(80):
            # Keep three measured text lanes even with Android's 130% font size.
            self.headline.font_size='16sp'
            self.subtitle.font_size=self.badge.font_size='8sp'
            self.headline.pos,self.headline.size=(left,self.y+dp(34)),(available,dp(30))
            self.subtitle.pos,self.subtitle.size=(left,self.y+dp(17)),(available,dp(17))
            self.badge.pos,self.badge.size=(left,self.y),(available,dp(17))
        else:
            self.headline.font_size='18sp' if narrow else '21sp'
            self.subtitle.font_size=self.badge.font_size='10sp'
            self.headline.pos,self.headline.size=(left,self.y+self.height*.55),(available,self.height*.45)
            self.subtitle.pos,self.subtitle.size=(left,self.y+self.height*.30),(available,self.height*.23)
            self.badge.pos,self.badge.size=(left,self.y+self.height*.02),(available,self.height*.26)
    def set_verified(self,verified):
        verified=verified is True
        if self._verified is verified:return
        self._verified=verified
        self.badge.text='官方資源驗證已完成' if verified else '官方資源尚未通過驗證'
        self.badge.color=_GREEN if verified else _CYAN


class CheckRow(BoxLayout):
    """Readable name and description, with the live state always visible."""
    _COLORS={
        'pending':(MUTED,'未確認','pending'),
        'checking':(_CYAN,'檢查中','refresh'),
        'passed':(_GREEN,'驗證成功','check-circle'),
        'blocked':(_RED,'未通過','error'),
    }
    def __init__(self,key,title,description,symbol,**kwargs):
        super().__init__(orientation='horizontal',size_hint_y=None,
                         height=dp(40),spacing=dp(8),padding=[dp(10),dp(4)],**kwargs)
        glow_panel(self,fill=_INNER,radius=11)
        self.mark=ReferenceGlyph(symbol,edge=23,pos_hint={'center_y':.5})
        self.add_widget(self.mark)
        words=BoxLayout(orientation='vertical',spacing=0)
        self.name_label=txt(title,size='12sp',height=18,bold=True)
        self.description=txt(description,size='9sp',height=14,color=MUTED)
        # Names/status never ellipsize. Descriptions grow on narrow screens or
        # larger system font scales instead of being silently cut away.
        self.description.bind(texture_size=self._fit_description)
        self.name_label.bind(texture_size=self._fit_description)
        words.add_widget(self.name_label); words.add_widget(self.description)
        self.add_widget(words)
        self.state_icon=ReferenceGlyph('pending',tint=ICON_DIM,edge=16,pos_hint={'center_y':.5})
        self.add_widget(self.state_icon)
        self.state=txt('未確認',size='10sp',height=22,color=MUTED,bold=True)
        self.state.size_hint_x=None; self.state.width=dp(48)
        self.state.halign='right'
        self.add_widget(self.state)
        self.key=key; self._current=None; self.compact=False
        self.bind(size=self._align_icons,pos=self._align_icons)
        self.update('pending')

    def set_compact(self,compact):
        self.compact=bool(compact)
        self.name_label.font_size='11sp'
        self.description.font_size='8.5sp'
        self.padding=[dp(9),dp(3)]
        self.description.opacity=0 if compact else 1
        self.mark.size=(dp(20 if compact else 23),)*2
        self._fit_description()

    def _fit_description(self,*_):
        self.name_label.height=max(dp(16),self.name_label.texture_size[1])
        self.description.height=0 if getattr(self,'compact',False) else max(dp(13),self.description.texture_size[1])
        self.height=max(dp(27 if getattr(self,'compact',False) else 35),
                        self.name_label.height+self.description.height+dp(6))

    def _align_icons(self,*_):
        self.mark.center_y=self.center_y
        self.state_icon.center_y=self.center_y
        self.state.height=self.height-dp(8)

    def update(self,kind):
        if kind==self._current:return
        self._current=kind
        color,caption,icon=self._COLORS.get(kind,self._COLORS['pending'])
        self.state.text=caption; self.state.color=color
        self.state_icon.icon=icon
        self.state_icon.set_tint(ICON_GREEN if kind=='passed' else ICON_RED if kind=='blocked' else ICON_CYAN if kind=='checking' else ICON_DIM)
        self.state_icon._paint()


class _AdaptiveRail(VerificationRail):
    """Connect actual row centres, including accessibility-driven wrapping."""
    def __init__(self,**kwargs):
        self.rows=[]
        super().__init__(**kwargs)
        self.width=dp(13)
    def _paint(self,*_):
        self.canvas.before.clear()
        if not self.rows:return
        ys=[row.center_y for row in self.rows]
        x=self.center_x
        with self.canvas.before:
            Color(.18,.76,.88,.3)
            Line(points=(x,ys[0],x,ys[-1]),width=dp(.7))
            for y,state in zip(ys,self.states):
                Color(*(ICON_GREEN if state=='passed' else ICON_RED if state=='blocked' else ICON_CYAN if state=='checking' else ICON_DIM))
                Ellipse(pos=(x-dp(2.5),y-dp(2.5)),size=(dp(5),dp(5)))


class _DetailsCard(ButtonBehavior,BoxLayout):
    """A full-size details target, separate from the frozen bottom actions."""


class VerificationDashboard(BoxLayout):
    """Single-screen overview with details on demand; the gate owns entry."""
    _ICONS=('cube','database','layers','document','bundle','gear','database')
    def __init__(self,retry,start_service,enter_login=None,**kwargs):
        super().__init__(orientation='vertical',**kwargs)
        with self.canvas.before:
            Color(*_SKY)
            background=Rectangle(pos=self.pos,size=self.size)
        self.bind(pos=lambda *_:setattr(background,'pos',self.pos),
                  size=lambda *_:setattr(background,'size',self.size))
        # There is deliberately no ScrollView in the first screen. Detailed
        # diagnostics open only after an explicit tap on the result card.
        self.viewport=BoxLayout(orientation='vertical')
        root=BoxLayout(orientation='vertical',padding=[dp(12),dp(3),dp(12),dp(9)],spacing=dp(8))
        self.hero=CosmicHeader()
        root.add_widget(self.hero)
        self.inspection=inspection=BoxLayout(orientation='vertical',size_hint_y=None,
                             padding=[dp(12),dp(8)],spacing=dp(6))
        inspection.bind(minimum_height=inspection.setter('height'))
        glow_panel(inspection,radius=19,bright=True)
        self.inspection_title_row=title_row=BoxLayout(size_hint_y=None,height=dp(27),spacing=dp(8))
        title_row.add_widget(ReferenceGlyph('layers',edge=22,pos_hint={'center_y':.5}))
        self.inspection_title=txt('官方資料與資料庫檢查',size='16sp',height=27,bold=True)
        title_row.add_widget(self.inspection_title)
        inspection.add_widget(title_row)
        self.caption=txt('核對官方來源與手機端資料。全部通過後，才能安全進入帳號登入。',size='11sp',color=MUTED)
        track=BoxLayout(orientation='horizontal',size_hint_y=None,spacing=dp(6))
        self.rail=_AdaptiveRail()
        track.add_widget(self.rail)
        self.steps_box=steps_box=BoxLayout(orientation='vertical',size_hint_y=None,spacing=dp(3))
        steps_box.bind(minimum_height=steps_box.setter('height'))
        steps_box.bind(height=lambda w,h:setattr(track,'height',h))
        self.rows={}
        for (key,name,description),symbol in zip(STEPS,self._ICONS):
            item=CheckRow(key,name,description,symbol)
            steps_box.add_widget(item); self.rows[key]=item
            item.bind(pos=self.rail._paint,size=self.rail._paint)
        self.rail.rows=list(self.rows.values())
        track.add_widget(steps_box);inspection.add_widget(track);root.add_widget(inspection)

        self.versions=versions=BoxLayout(orientation='vertical',size_hint_y=None,
                           padding=[dp(12),dp(5)],spacing=0)
        versions.bind(minimum_height=versions.setter('height'))
        glow_panel(versions,radius=16)
        self.version_cards=cards=BoxLayout(size_hint_y=None,height=dp(40),spacing=dp(10))
        self.version_labels={};self.version_captions={};version_cards=[]
        def fit_versions(*_):
            cards.height=max([dp(36)]+[card.minimum_height for card in version_cards])
        for name in ('DataPackage','MainPackage'):
            card=BoxLayout(orientation='vertical',spacing=0,size_hint_y=None)
            card.bind(minimum_height=card.setter('height'));card.bind(minimum_height=fit_versions)
            caption=grow(txt(name,size='10sp',height=17,color=MUTED),minimum=17)
            value=grow(txt('尚未取得',size='12sp',height=20,color=_CYAN,bold=True),minimum=20)
            card.add_widget(caption);card.add_widget(value)
            self.version_labels[name]=value;self.version_captions[name]=caption
            cards.add_widget(card);version_cards.append(card)
        versions.add_widget(cards);root.add_widget(versions)

        self.result_card=result=_DetailsCard(orientation='vertical',size_hint_y=None,
                         padding=[dp(12),dp(5)],spacing=1)
        result.bind(minimum_height=lambda w,h:setattr(w,'height',max(dp(44),h)))
        result.bind(on_release=lambda *_:self.open_details())
        glow_panel(result,radius=16)
        self.status_row=status_row=BoxLayout(size_hint_y=None,height=dp(24),spacing=dp(8))
        status_row.add_widget(ReferenceGlyph('pulse',edge=20,pos_hint={'center_y':.5}))
        self.status=txt('等待背景服務連線',size='12sp',color=_CYAN,height=24,bold=True)
        status_row.add_widget(self.status);result.add_widget(status_row)
        self.details_hint=txt('點此查看完整檢查結果與說明',size='9sp',height=16,color=MUTED)
        result.add_widget(self.details_hint);root.add_widget(result)
        # Keep exact details and time available without forcing a page scroll.
        self.detail=txt('尚無檢查結果。',size='11sp',color=MUTED)
        self.checked=txt('檢查時間：尚未取得',size='10sp',color=MUTED)
        self._details_popup=None;self._details_label=None
        self.spacer=Widget();root.add_widget(self.spacer)
        self.viewport.add_widget(root);self.add_widget(self.viewport)
        self.content_root=root
        controls=BoxLayout(orientation='vertical',size_hint_y=None,
                           padding=[dp(12),dp(8),dp(12),dp(12)],spacing=dp(6))
        controls.bind(minimum_height=controls.setter('height'))
        self.action_row=action_row=BoxLayout(size_hint_y=None,height=dp(46),spacing=dp(8))
        self.retry=NeonAction('重新檢查',retry,primary=True,glyph='refresh')
        self.service_button=NeonAction('啟動／重連接',start_service,glyph='wifi')
        self.retry.compact_caption();self.service_button.compact_caption()
        action_row.add_widget(self.retry)
        action_row.add_widget(self.service_button)
        controls.add_widget(action_row)
        self.enter_login=NeonAction('進入帳號登入',enter_login or (lambda:None),primary=True,glyph='play')
        self.enter_login.disabled=True
        self.enter_login.height=dp(42)
        controls.add_widget(self.enter_login)
        self.add_widget(controls)
        self.actions=controls

        self._last_render=None
        self._animation_app=None
        self._animation_paused=False
        self._animation_ancestors=[]
        self.viewport.bind(size=self._adapt_layout)
        self._adapt_layout()

    def on_parent(self,*_):
        if not hasattr(self,'rows'):return
        # Parent may stay unchanged while a whole old root is removed on resume.
        # Watch every ancestor so an invisible tree cannot retain a live clock.
        for ancestor in getattr(self,'_animation_ancestors',[]):
            ancestor.unbind(parent=self._ancestor_changed)
        self._animation_ancestors=[]
        ancestor=self.parent
        while (ancestor is not None and hasattr(ancestor,'parent')
               and ancestor.parent is not ancestor
               and ancestor not in self._animation_ancestors):
            ancestor.bind(parent=self._ancestor_changed)
            self._animation_ancestors.append(ancestor)
            ancestor=ancestor.parent
        app=App.get_running_app() if self.get_root_window() is not None else None
        previous=getattr(self,'_animation_app',None)
        if previous is not None and previous is not app:
            previous.unbind(on_pause=self._pause_animation,on_resume=self._resume_animation,
                            on_stop=self._stop_animation)
        self._animation_app=app
        if app is not None and previous is not app:
            app.bind(on_pause=self._pause_animation,on_resume=self._resume_animation,
                     on_stop=self._stop_animation)
        self._sync_animations()

    def _ancestor_changed(self,*_):
        self.on_parent()

    def _sync_animations(self):
        active=self.get_root_window() is not None and not getattr(self,'_animation_paused',False)
        for row in self.rows.values():
            row.state_icon.set_animating(active and row._current=='checking')

    def _pause_animation(self,*_):
        self._animation_paused=True
        self._sync_animations()

    def _resume_animation(self,*_):
        self._animation_paused=False
        self._sync_animations()

    def _stop_animation(self,*_):
        self._pause_animation()
        app=self._animation_app
        if app is not None:
            app.unbind(on_pause=self._pause_animation,on_resume=self._resume_animation,
                       on_stop=self._stop_animation)
            self._animation_app=None

    def _adapt_layout(self,*_):
        compact=(self.viewport.height<dp(610) or
                 (Metrics.fontscale>1.15 and self.viewport.height<dp(720)))
        self.compact=compact
        self.hero.height=dp(64 if compact else 96)
        self.content_root.spacing=dp(5 if compact else 8)
        self.content_root.padding=[dp(12),dp(2),dp(12),dp(6 if compact else 9)]
        self.inspection.padding=[dp(12),dp(6 if compact else 8)]
        self.inspection.spacing=dp(5 if compact else 6)
        self.inspection_title.font_size='14sp' if compact else '16sp'
        self.inspection_title.height=dp(30 if Metrics.fontscale>1.15 else 24 if compact else 27)
        self.inspection_title_row.height=self.inspection_title.height+dp(1)
        self.status.font_size='11sp' if compact else '12sp'
        self.details_hint.font_size='8sp' if compact else '9sp'
        for row in self.rows.values():row.set_compact(compact)
        for caption in self.version_captions.values():caption.font_size='9sp' if compact else '10sp'
        for value in self.version_labels.values():value.font_size='10sp' if compact else '12sp'

    def _details_text(self):
        sections=[self.status.text,self.detail.text,self.checked.text,self.caption.text]
        sections.extend(row.name_label.text+'：'+row.state.text+'\n'+row.description.text for row in self.rows.values())
        return '\n\n'.join(sections)

    def open_details(self):
        if self._details_popup is not None:return self._details_popup
        frame=BoxLayout(orientation='vertical',padding=dp(14),spacing=dp(10))
        glow_panel(frame,radius=20,bright=True)
        scroll=ScrollView(do_scroll_x=False)
        body=grow(txt(self._details_text(),size='13sp',height=40),minimum=40)
        scroll.add_widget(body);frame.add_widget(scroll)
        close=Button(text='關閉',size_hint_y=None,height=dp(46),background_normal='',
                     background_color=(.015,.45,.54,1),color=TEXT,font_size='14sp')
        frame.add_widget(close)
        popup=Popup(title='完整檢查資訊',content=frame,size_hint=(.94,.84),
                    background='',background_color=_SKY,separator_color=_CYAN)
        self._details_popup=popup;self._details_label=body
        close.bind(on_release=lambda *_:popup.dismiss())
        def dismissed(*_):self._details_popup=None;self._details_label=None
        popup.bind(on_dismiss=dismissed);popup.open()
        return popup

    def apply_state(self,service,local,*,connected,detail,login_ready=False):
        view=view_state(service,local,connected=connected,login_ready=login_ready)
        detail=detail[:550] if type(detail) is str else '檢查資料暫時無法讀取'
        revision=(tuple(sorted(view['steps'].items())),tuple(sorted(view['versions'].items())),
                  view['headline'],view['kind'],view['checked_at_utc'],view['approved'],detail)
        if revision==self._last_render:return
        self._last_render=revision
        self.hero.set_verified(view['approved'])
        self.enter_login.disabled = not view['approved']
        self.rail.set_states([view['steps'][key] for key,_,_ in STEPS])
        for key,step in self.rows.items():step.update(view['steps'][key])
        self._sync_animations()
        for name,label in self.version_labels.items():
            label.text=view['versions'].get(name) or '尚未取得'
        self.status.text=view['headline']
        self.status.color=_GREEN if view['approved'] else _RED if view['kind']=='blocked' else _CYAN
        self.detail.text=detail
        checked=view['checked_at_utc']
        self.checked.text='檢查時間（UTC）：'+checked if checked else '檢查時間：尚未取得'
        if self._details_label is not None:self._details_label.text=self._details_text()
