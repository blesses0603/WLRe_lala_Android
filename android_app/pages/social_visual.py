"""Lightweight, real-data visual primitives for Android chat and party.

All pictograms are Canvas geometry (not unsupported Unicode). Never depict
a fabricated player portrait, online total, distance, invitation or receipt.
No continuous animation, textures, network calls or chat commands here.
"""
from math import cos, sin, pi

from kivy.graphics import Color, Ellipse, Line, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.widget import Widget

from android_app.theme import ACCENT, MUTED, TEXT, SOFT, SURFACE, BORDER, neon_surface, style_button


class SocialIcon(Widget):
    """Small normalized line-art symbols that scale on 320dp–wide phones."""

    def __init__(self, symbol="chat", tint=ACCENT, edge=23, **kwargs):
        self.symbol, self.tint = symbol, tint
        super().__init__(size_hint=(None, None),
                         size=(dp(edge), dp(edge)), **kwargs)
        self.bind(size=self._paint, pos=self._paint)
        self._paint()

    def colorize(self, tint):
        self.tint = tint
        self._paint()

    def _paint(self, *_):
        self.canvas.before.clear()
        scale = min(self.width, self.height) / 24.0
        ox = self.center_x - 12 * scale
        oy = self.center_y - 12 * scale

        def p(x, y):
            return (ox + x * scale, oy + y * scale)

        def lines(*points, closed=False, thick=1.8):
            coords = []
            for x, y in points:
                coords.extend(p(x, y))
            Line(points=coords, close=closed, width=dp(thick),
                 joint="round", cap="round")

        def circ(x, y, radius, fill=False):
            px, py = p(x, y)
            if fill:
                Ellipse(pos=(px-radius*scale,py-radius*scale),
                        size=(2*radius*scale,2*radius*scale))
            else:
                Line(circle=(px,py,radius*scale),width=dp(1.8))

        def rect(x, y, w, h, radius=2):
            px,py = p(x,y)
            Line(rounded_rectangle=(px,py,w*scale,h*scale,radius*scale),
                 width=dp(1.8))

        with self.canvas.before:
            Color(*self.tint)
            symbol = self.symbol
            if symbol in ("chat", "message"):
                rect(2, 5, 20, 16, 4)
                lines((7,5),(5,1),(12,5))
                for x in (8,12,16): circ(x,13,0.9,True)
            elif symbol in ("users", "party"):
                circ(9,17,4)
                circ(18,16,3)
                lines((1,4),(1,7),(4,12),(14,12),(17,7),(17,4))
                lines((18,11),(21,10),(23,6),(23,4))
            elif symbol in ("user", "person", "invite"):
                circ(11,17,4)
                lines((3,2),(3,7),(6,11),(16,11),(19,7),(19,2))
                if symbol == "invite":
                    lines((19,15),(19,23))
                    lines((15,19),(23,19))
            elif symbol in ("send", "plane"):
                lines((2,12),(22,22),(15,2),(12,10),(2,12),closed=True)
                lines((12,10),(22,22))
            elif symbol == "megaphone":
                lines((3,9),(8,9),(20,16),(20,5),(8,11),(3,11),closed=True)
                lines((7,9),(10,3),(13,3),(12,10))
            elif symbol == "pin":
                circ(12,15,3)
                lines((12,1),(5,11),(5,17),(8,21),(12,23),
                      (16,21),(19,17),(19,11),(12,1),closed=True)
            elif symbol in ("check", "shield"):
                if symbol == "shield":
                    lines((12,2),(20,6),(20,18),(12,22),(4,18),(4,6),
                          (12,2),closed=True)
                lines((6,12),(10,8),(18,17),thick=2.3)
            elif symbol == "heart":
                lines((12,3),(3,12),(3,17),(7,21),(12,18),
                      (17,21),(21,17),(21,12),(12,3),closed=True)
            elif symbol == "smile":
                circ(12,12,10)
                circ(8,15,1,True); circ(16,15,1,True)
                Line(ellipse=(*p(6,7),12*scale,7*scale,180,360),
                     width=dp(1.8))
            elif symbol == "flame":
                lines((12,2),(6,6),(4,11),(7,15),(10,20),
                      (10,14),(15,21),(20,13),(19,7),(12,2),closed=True)
            elif symbol == "sparkle":
                lines((12,1),(15,9),(23,12),(15,15),(12,23),
                      (9,15),(1,12),(9,9),(12,1),closed=True)
            elif symbol == "thumb":
                lines((3,3),(3,13),(8,13),(12,22),(14,22),
                      (15,14),(22,14),(20,3),(8,3),(3,3),closed=True)
            elif symbol == "crown":
                lines((2,7),(22,7),(19,20),(13,13),(8,20),
                      (5,13),(2,7),closed=True)
            elif symbol in ("chevron", "arrow"):
                lines((6,16),(12,9),(18,16),thick=2.3)
            elif symbol == "refresh":
                Line(circle=(*p(12,12),8*scale,40,315),width=dp(2))
                lines((18,19),(20,18),(20,12))
            elif symbol == "list":
                for y in (6,12,18):
                    circ(4,y,1,True)
                    lines((8,y),(22,y))
            elif symbol in ("bell", "notice"):
                lines((5,8),(8,12),(8,18),(11,21),(14,21),
                      (17,18),(17,12),(20,8),(5,8))
                lines((10,5),(14,5))
                circ(12,3,1,True)
            elif symbol == "settings":
                for i in range(16):
                    angle = i*pi/8
                    rad = 10 if i%2==0 else 8
                    jangle = (i+1)*pi/8
                    nxt = 10 if (i+1)%2==0 else 8
                    lines((12+rad*cos(angle),12+rad*sin(angle)),
                          (12+nxt*cos(jangle),12+nxt*sin(jangle)))
                circ(12,12,3)
            elif symbol == "home":
                lines((2,11),(12,22),(22,11))
                lines((5,12),(5,3),(19,3),(19,12))
                lines((10,3),(10,10),(14,10),(14,3))
            elif symbol in ("layers", "stack"):
                for i in (0,-5,-10):
                    lines((2,16+i),(12,21+i),(22,16+i))
                    lines((2,16+i),(12,11+i),(22,16+i))
            elif symbol in ("bars", "chart"):
                rect(2,2,4,9,0.8);rect(10,2,4,17,0.8);rect(18,2,4,13,0.8)
            elif symbol == "grid":
                for x in (3,14):
                    for y in (3,14):
                        rect(x,y,8,8,1.2)
            elif symbol == "close":
                lines((5,5),(19,19));lines((5,19),(19,5))
            else:
                circ(12,12,9)


def caption(text, *, size='12sp', color=MUTED, height=28, bold=False):
    view = Label(text=str(text), font_size=size, color=color,
                 bold=bold, size_hint_y=None, height=dp(height),
                 halign='left', valign='middle', shorten=True,
                 shorten_from='right')
    view.bind(width=lambda w, width: setattr(
        w, 'text_size', (max(0,width-dp(3)), None)))
    return view


class SocialButton(Button):
    """Touch-safe labeled action with a vector icon, no missing glyph boxes."""

    def __init__(self, title, callback, *, icon='chat', primary=False,
                 height=40, font='12sp', **kwargs):
        super().__init__(text=title, size_hint_y=None, height=dp(height),
                         font_size=font, **kwargs)
        style_button(self, primary=primary, radius=12)
        self.halign='center'
        self.valign='middle'
        self.glyph=SocialIcon(icon, edge=19)
        self.add_widget(self.glyph)
        self.bind(pos=self._place_glyph, size=self._place_glyph)
        self.bind(on_release=lambda *_: callback())
        self._place_glyph()

    def _place_glyph(self, *_):
        self.glyph.pos=(self.x+dp(6),
                        self.center_y-self.glyph.height/2)
        self.text_size=(max(0,self.width-dp(16)),self.height)


def heading(title, *, icon='chat', subtitle=None, color=TEXT):
    panel=BoxLayout(orientation='horizontal',size_hint_y=None,
                    height=dp(32),spacing=dp(7))
    panel.add_widget(SocialIcon(icon, edge=25))
    labels=BoxLayout(orientation='vertical')
    labels.add_widget(caption(title,size='16sp',color=color,height=24,bold=True))
    if subtitle:
        labels.add_widget(caption(subtitle,size='10sp',height=16))
        panel.height=dp(43)
    panel.add_widget(labels)
    return panel


def glass_card(*, bright=False, padding=8, gap=6, radius=16):
    panel=BoxLayout(orientation='vertical', size_hint_y=None,
                    padding=dp(padding),spacing=dp(gap))
    panel.bind(minimum_height=panel.setter('height'))
    neon_surface(panel,color=SOFT if bright else SURFACE,
                 radius=radius,border=BORDER,bright=bright)
    return panel


class MessageTile(BoxLayout):
    """Tappable server-synced chat bubble, not a fabricated character portrait."""

    def __init__(self, name, channel, body, *, own=False, reply=None,
                 when=None, callback=None, **kwargs):
        super().__init__(orientation='horizontal',size_hint_y=None,
                         spacing=dp(7),padding=[dp(2),dp(3),dp(2),dp(3)],
                         **kwargs)
        self.bind(minimum_height=self.setter('height'))
        avatar=Widget(size_hint=(None,None),size=(dp(31),dp(31)))
        with avatar.canvas.before:
            Color(.10,.65,.80,.35)
            round_back=RoundedRectangle(radius=[dp(16)])
        def paint(*_):
            round_back.pos=avatar.pos
            round_back.size=avatar.size
        avatar.bind(pos=paint,size=paint);paint()
        icon=SocialIcon('user',edge=23)
        avatar.add_widget(icon)
        avatar.bind(pos=lambda *_: setattr(icon,'center',avatar.center))
        icon.center=avatar.center
        self.add_widget(avatar)

        column=BoxLayout(orientation='vertical',size_hint_y=None,
                         spacing=dp(2))
        column.bind(minimum_height=column.setter('height'))
        top=BoxLayout(size_hint_y=None,height=dp(19),spacing=dp(5))
        top.add_widget(caption(name,size='12sp',color=ACCENT if own else TEXT,
                                height=19,bold=True))
        top.add_widget(caption(channel,size='10sp',height=19))
        if when:
            time_label=caption(when,size='10sp',height=19)
            time_label.halign='right'
            top.add_widget(time_label)
        column.add_widget(top)

        bubble=Button(text=body or ' ',size_hint_y=None,height=dp(42),
                      halign='left',valign='middle',font_size='12sp')
        style_button(bubble,primary=own,radius=13)
        bubble.bind(width=lambda w,width:setattr(
            w,'text_size',(max(0,width-dp(16)),None)))
        bubble.bind(texture_size=lambda w,s:setattr(
            w,'height',max(dp(39),s[1]+dp(14))))
        if callback:
            bubble.bind(on_release=lambda *_: callback())
        column.add_widget(bubble)
        if reply:
            note=caption('引用：'+str(reply),size='10sp',
                          height=24,color=MUTED)
            column.add_widget(note)
        self.add_widget(column)


class NearbyTile(BoxLayout):
    """Actual nearby player with explicit invite/application choices."""

    def __init__(self, name, rid, detail, invite, apply, **kwargs):
        super().__init__(orientation='horizontal',size_hint_y=None,
                         height=dp(53),padding=[dp(4),dp(5)],
                         spacing=dp(5),**kwargs)
        neon_surface(self,color=SOFT,radius=13)
        self.add_widget(SocialIcon('user',edge=31))
        summary=BoxLayout(orientation='vertical')
        summary.add_widget(caption(name,size='12sp',color=TEXT,
                                   height=23,bold=True))
        summary.add_widget(caption(detail,size='10sp',height=20))
        self.add_widget(summary)
        buttons=BoxLayout(size_hint_x=None,width=dp(113),
                          spacing=dp(4))
        first=SocialButton('邀請',invite,icon='invite',height=34,font='10sp')
        second=SocialButton('申請',apply,icon='users',height=34,font='10sp')
        # Expand across the parent row's height; labels remain 48dp+ touch.
        first.size_hint_y=1;second.size_hint_y=1
        buttons.add_widget(first);buttons.add_widget(second)
        self.add_widget(buttons)
