"""Shared rounded sci-fi UI for every Kivy mobile surface.

Decorative drawing belongs to reusable widgets, not individual feature pages.
No networking or game state is handled by this module.
"""
from kivy.graphics import Color, RoundedRectangle, Ellipse
from kivy.metrics import dp

BACKGROUND = (0.035, 0.055, 0.105, 1)
SURFACE = (0.080, 0.130, 0.205, 0.98)
TEXT = (0.925, 0.965, 1.0, 1)
MUTED = (0.60, 0.73, 0.82, 1)
ACCENT = (0.31, 0.84, 0.94, 1)
SOFT = (0.115, 0.240, 0.330, 1)
DANGER = (1.0, 0.47, 0.53, 1)
BORDER = (0.22, 0.49, 0.62, 0.75)

PRIMARY_FILL = (0.065, 0.45, 0.58, 1)
PRIMARY_PRESSED = (0.035, 0.33, 0.43, 1)
BUTTON_PRESSED = (0.13, 0.35, 0.47, 1)
DANGER_FILL = (0.26, 0.105, 0.16, 1)
DANGER_PRESSED = (0.37, 0.13, 0.19, 1)
DISABLED_FILL = (0.09, 0.14, 0.20, 0.7)
INPUT_FILL = (0.045, 0.085, 0.15, 1)
FOCUS_FILL = (0.06, 0.14, 0.22, 1)


def _rounded(view, fill, border, radius):
    """Create a resize-aware border and inset panel in canvas.before."""
    with view.canvas.before:
        outer_tint = Color(*border)
        outer = RoundedRectangle(pos=view.pos, size=view.size, radius=[dp(radius)])
        inner_tint = Color(*fill)
        inner = RoundedRectangle(pos=view.pos, size=view.size,
                                 radius=[dp(max(1, radius - 1))])

    def geometry(*_):
        inset = dp(1)
        outer.pos, outer.size = view.pos, view.size
        inner.pos = (view.x + inset, view.y + inset)
        inner.size = (max(0, view.width - 2 * inset), max(0, view.height - 2 * inset))

    geometry()
    view.bind(pos=geometry, size=geometry)
    return outer_tint, inner_tint


def surface(view, color=SURFACE, radius=22, border=BORDER):
    """Transparent-gap-friendly rounded cards, including resize on text wrap."""
    if hasattr(view, '_lala_surface_colors'):
        outer, inside = view._lala_surface_colors
        outer.rgba, inside.rgba = border, color
        return view
    view._lala_surface_colors = _rounded(view, color, border, radius)
    return view


def style_button(view, primary=False, danger=False, radius=18):
    """Shared visual states for Buttons, Spinners and dropdown SpinnerOptions."""
    view.background_normal = ''
    view.background_down = ''
    view.background_disabled_normal = ''
    view.background_color = (0, 0, 0, 0)
    view.font_size = '14sp'
    view.halign, view.valign = 'center', 'middle'
    view.disabled_color = MUTED
    view._lala_button_variant = 'danger' if danger else ('primary' if primary else 'default')

    if not hasattr(view, '_lala_button_colors'):
        view._lala_button_colors = _rounded(view, SOFT, BORDER, radius)
        view.bind(size=lambda w, size: setattr(
            w, 'text_size', (max(0, size[0] - dp(16)), size[1])))

        def update(*_):
            edge, fill = view._lala_button_colors
            variant = view._lala_button_variant
            pressed = getattr(view, 'state', 'normal') == 'down'
            if view.disabled:
                fill.rgba, edge.rgba = DISABLED_FILL, (0.16, 0.27, 0.34, 0.45)
                view.color = MUTED
            elif variant == 'primary':
                fill.rgba = PRIMARY_PRESSED if pressed else PRIMARY_FILL
                edge.rgba, view.color = ACCENT, TEXT
            elif variant == 'danger':
                fill.rgba = DANGER_PRESSED if pressed else DANGER_FILL
                edge.rgba, view.color = DANGER, (1, 0.82, 0.84, 1)
            else:
                fill.rgba = BUTTON_PRESSED if pressed else SOFT
                edge.rgba, view.color = BORDER, TEXT

        view._lala_button_refresh = update
        view.bind(state=update, disabled=update)
    view._lala_button_refresh()
    return view


def style_input(view, radius=16):
    """Rounded text inputs with a distinct focus ring, preserving Android IME."""
    view.background_normal = ''
    view.background_active = ''
    view.background_color = (0, 0, 0, 0)
    view.foreground_color = TEXT
    view.hint_text_color = MUTED
    view.cursor_color = ACCENT
    view.selection_color = (0.16, 0.47, 0.60, 0.60)
    view.padding = [dp(14), dp(12), dp(14), dp(12)]
    if not hasattr(view, '_lala_input_colors'):
        view._lala_input_colors = _rounded(view, INPUT_FILL, BORDER, radius)

        def update(*_):
            edge, fill = view._lala_input_colors
            edge.rgba = ACCENT if view.focus else BORDER
            fill.rgba = FOCUS_FILL if view.focus else INPUT_FILL

        view._lala_input_refresh = update
        view.bind(focus=update)
    view._lala_input_refresh()
    return view


def style_checkbox(view):
    """Replace square default check art with an accent circular toggle."""
    for name in ("background_checkbox_normal", "background_checkbox_down",
                 "background_checkbox_disabled_normal", "background_checkbox_disabled_down"):
        setattr(view, name, "")
    if not hasattr(view, '_lala_check_parts'):
        with view.canvas.after:
            border = Color(*BORDER)
            outer = Ellipse()
            middle = Color(*INPUT_FILL)
            core = Ellipse()
            dot_color = Color(*ACCENT)
            dot = Ellipse()

        def update(*_):
            diameter = min(dp(24), view.width - dp(6), view.height - dp(6))
            x, y = view.center_x - diameter / 2, view.center_y - diameter / 2
            outer.pos, outer.size = (x, y), (diameter, diameter)
            core.pos, core.size = (x + dp(2), y + dp(2)), (
                max(0, diameter - dp(4)), max(0, diameter - dp(4)))
            dot.pos, dot.size = (x + dp(7), y + dp(7)), (
                max(0, diameter - dp(14)), max(0, diameter - dp(14)))
            border.rgba = MUTED if view.disabled else ACCENT
            dot_color.rgba = ACCENT if view.active and not view.disabled else (
                (0, 0, 0, 0) if not view.active else MUTED)

        view._lala_check_parts = (border, outer, middle, core, dot_color, dot)
        view.bind(pos=update, size=update, active=update, disabled=update)
    else:
        update = None
    if update:
        update()
    return view
