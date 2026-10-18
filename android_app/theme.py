"""Shared rounded sci-fi UI for every Kivy mobile surface.

Decorative drawing belongs to reusable widgets, not individual feature pages.
No networking or game state is handled by this module.
"""
from pathlib import Path

from kivy.graphics import Color, RoundedRectangle, Ellipse, InstructionGroup
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
# Inputs use an opaque bright fill with dark glyphs so both native Android IME
# composition and Kivy's TextInput rendering remain readable across devices.
# These colors intentionally contrast with the dark surrounding cards.
INPUT_FILL = (0.87, 0.93, 0.97, 1)
FOCUS_FILL = (0.97, 0.985, 1, 1)
INPUT_TEXT = (0.035, 0.075, 0.13, 1)
INPUT_HINT = (0.31, 0.38, 0.45, 1)
INPUT_CARET = (0.025, 0.34, 0.49, 1)
INPUT_SELECTION = (0.28, 0.68, 0.81, 0.40)
INPUT_FONT = str(Path(__file__).resolve().parent / "assets/fonts/NotoSansTC-Regular.ttf")


def _rounded(view, fill, border, radius, under_existing=False):
    """Create resize-aware rounded paint, with an optional lowest draw layer.

    Kivy TextInput may render its hint and editable line textures in
    canvas.before. Appending an opaque rectangle there can hide BOTH the
    typed glyphs and the hint even when foreground_color is correct.
    Keep text fields' backgrounds at instruction index zero.
    """
    group = InstructionGroup()
    outer_tint = Color(*border)
    outer = RoundedRectangle(pos=view.pos, size=view.size, radius=[dp(radius)])
    inner_tint = Color(*fill)
    inner = RoundedRectangle(pos=view.pos, size=view.size,
                             radius=[dp(max(1, radius - 1))])
    for instruction in (outer_tint, outer, inner_tint, inner):
        group.add(instruction)
    if under_existing:
        # TextInput can inherit the GL color left by custom canvas.before
        # instructions. The next text/hint glyphs must never inherit
        # the light background color, or they disappear on a light input.
        glyph_color = Color(*view.foreground_color)
        group.add(glyph_color)
        view._lala_input_glyph_color = glyph_color
        view.canvas.before.insert(0, group)
    else:
        view.canvas.before.add(group)

    def geometry(*_):
        inset = dp(1)
        outer.pos, outer.size = view.pos, view.size
        inner.pos = (view.x + inset, view.y + inset)
        inner.size = (max(0, view.width - 2 * inset), max(0, view.height - 2 * inset))

    geometry()
    view.bind(pos=geometry, size=geometry)
    if under_existing:
        view._lala_input_background_group = group
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
    """Opaque high-contrast inputs with readable IME composition and focus ring."""
    view.background_normal = ''
    view.background_active = ''
    view.background_color = (0, 0, 0, 0)
    # Use the actual bundled Chinese font for hint text and typed text,
    # independently of LabelBase's global font alias registration order.
    view.font_name = INPUT_FONT
    # TextInput.foreground_color governs typed text AND IME composition.
    # Do not inherit a dark or semi-transparent color from any default theme.
    view.foreground_color = INPUT_TEXT
    view.disabled_foreground_color = INPUT_HINT
    view.hint_text_color = INPUT_HINT
    view.cursor_color = INPUT_CARET
    view.selection_color = INPUT_SELECTION
    view.padding = [dp(14), dp(12), dp(14), dp(12)]
    if not hasattr(view, '_lala_input_colors'):
        view._lala_input_colors = _rounded(
            view, INPUT_FILL, BORDER, radius, under_existing=True)

        def update(*_):
            edge, fill = view._lala_input_colors
            edge.rgba = ACCENT if view.focus else BORDER
            fill.rgba = FOCUS_FILL if view.focus else INPUT_FILL

        view._lala_input_refresh = update
        view.bind(focus=update)

        def update_text_tint(*_):
            if view.disabled:
                tint = view.disabled_foreground_color
            elif view.text:
                tint = view.foreground_color
            else:
                tint = view.hint_text_color
            view._lala_input_glyph_color.rgba = tint

        view._lala_input_tint_refresh = update_text_tint
        view.bind(text=update_text_tint, disabled=update_text_tint,
                  foreground_color=update_text_tint,
                  hint_text_color=update_text_tint,
                  disabled_foreground_color=update_text_tint)
    view._lala_input_refresh()
    view._lala_input_tint_refresh()
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
