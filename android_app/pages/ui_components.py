"""Reusable Android stage-two feature cards; no network or command logic.

Only inexpensive Kivy canvas shapes. Cards grow with their children on narrow
phones, leaving state, commands, and server confirmation with existing pages.
"""
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label

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
