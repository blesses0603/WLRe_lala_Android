"""Shared mobile colours and surfaces; no connection state lives here."""
from kivy.graphics import Color, RoundedRectangle
from kivy.metrics import dp

BACKGROUND = (0.95, 0.96, 0.97, 1)
SURFACE = (1, 1, 1, 1)
TEXT = (0.12, 0.19, 0.23, 1)
MUTED = (0.38, 0.45, 0.49, 1)
ACCENT = (0.06, 0.43, 0.43, 1)
SOFT = (0.88, 0.94, 0.94, 1)
DANGER = (0.67, 0.23, 0.25, 1)


def surface(view, color=SURFACE, radius=16):
    with view.canvas.before:
        Color(*color)
        shape = RoundedRectangle(pos=view.pos, size=view.size, radius=[dp(radius)])
    def update(*_):
        shape.pos, shape.size = view.pos, view.size
    view.bind(pos=update, size=update)
    return view


def style_button(view, primary=False, danger=False):
    view.background_normal = view.background_down = ''
    view.background_disabled_normal = ''
    view.background_color = ACCENT if primary else SOFT
    view.color = (1, 1, 1, 1) if primary else (DANGER if danger else ACCENT)
    view.disabled_color = MUTED
    view.font_size = '14sp'
    view.halign, view.valign = 'center', 'middle'
    view.bind(size=lambda w, size: setattr(w, 'text_size', (max(0, size[0] - dp(16)), size[1])))
    return view


def style_input(view):
    view.background_normal = view.background_active = ''
    view.background_color = BACKGROUND
    view.foreground_color = TEXT
    view.hint_text_color = MUTED
    view.cursor_color = ACCENT
    view.padding = [dp(12), dp(12)]
    return view
