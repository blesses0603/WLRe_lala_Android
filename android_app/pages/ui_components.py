"""Reusable Android stage-two feature cards; no network or command logic.

Only inexpensive Kivy canvas shapes. Cards grow with their children on narrow
phones, leaving state, commands, and server confirmation with existing pages.
"""
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.widget import Widget
from kivy.graphics import Color, RoundedRectangle

from android_app.theme import style_button

from android_app.theme import ACCENT, MUTED, SOFT, SURFACE, TEXT, BORDER, surface
from android_app.ui_shell import section_title


def feature_card(title, subtitle='', *, variant='normal'):
    panel = BoxLayout(orientation='vertical', size_hint_y=None,
                      padding=[dp(12), dp(10), dp(12), dp(12)],
                      spacing=dp(9))
    panel.bind(minimum_height=panel.setter('height'))
    shade = SOFT if variant == 'highlight' else SURFACE
    surface(panel, color=shade, border=BORDER, radius=19)
    panel.add_widget(section_title(title, subtitle))
    return panel


def status_line(text='等待同步', *, prominent=False):
    label = Label(text=text, color=ACCENT if prominent else MUTED,
                  font_size='14sp', halign='left', valign='middle',
                  size_hint_y=None, height=dp(38))
    # Avoid width-unbounded label textures and text clipping on 320dp.
    label.bind(width=lambda view, width: setattr(
        view, 'text_size', (max(0, width - dp(8)), None)))
    label.bind(texture_size=lambda view, size: setattr(
        view, 'height', max(dp(38), size[1] + dp(10))))
    return label


def summary_card(title, initial='等待伺服器同步'):
    panel = feature_card(title, variant='highlight')
    value = status_line(initial, prominent=True)
    panel.add_widget(value)
    return panel, value


def fixed_header(label, caption=''):
    """Compact feature subheading reused in map, chat and inventory."""
    return section_title(label, caption)


class StatMeter(BoxLayout):
    """A low-cost status bar: never infers HP/SP from absent game data."""

    def __init__(self, name, tint=ACCENT, **kwargs):
        super().__init__(orientation='vertical', size_hint_y=None,
                         height=dp(57), spacing=dp(3), **kwargs)
        self.name=name
        self.ratio=0.0
        self.caption=status_line(name + '：等待同步')
        self.caption.font_size='13sp'
        self.caption.height=dp(34)
        self.add_widget(self.caption)
        rail=Widget(size_hint_y=None, height=dp(9))
        with rail.canvas.before:
            Color(*SOFT)
            background=RoundedRectangle(radius=[dp(5)])
            Color(*tint)
            fill=RoundedRectangle(radius=[dp(5)])
        def resize(*_):
            background.pos=rail.pos
            background.size=rail.size
            fill.pos=rail.pos
            fill.size=(rail.width*self.ratio, rail.height)
        rail.bind(pos=resize, size=resize)
        self.rail=rail
        self._resize=resize
        self.add_widget(rail)
        resize()

    def set_value(self, current, maximum):
        if (type(current) is int and current >= 0 and
                type(maximum) is int and maximum > 0):
            self.ratio=min(1.0, current/maximum)
            self.caption.text='{}：{} / {}'.format(self.name,current,maximum)
        else:
            self.ratio=0.0
            self.caption.text=self.name+'：等待伺服器同步'
        self._resize()


def message_button(body, callback, *, own=False):
    """Readable bubble with real tap actions; no fabricated read receipts."""
    lines=max(1, (len(body)+19)//20)
    height=max(dp(66),min(dp(210),dp(40+24*lines)))
    view=Button(text=body, size_hint_y=None, height=height)
    style_button(view,primary=own,radius=17)
    view.halign='left'
    view.valign='middle'
    view.font_size='13sp'
    view.bind(size=lambda w,size:setattr(
        w,'text_size',(max(0,size[0]-dp(24)),size[1]-dp(10))))
    view.bind(on_release=lambda *_:callback())
    return view
