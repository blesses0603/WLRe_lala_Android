"""Scalable Canvas icons for the pre-login verification screen.

Native Kivy vector geometry: no unsupported Unicode, bitmap placeholder,
animation timer, external icon font, or status inferred from artwork.
"""
from math import cos, pi, sin

from kivy.graphics import Color, Ellipse, Line
from kivy.metrics import dp
from kivy.uix.widget import Widget

CYAN = (0.43, 0.96, 1.0, 1)
GREEN = (0.48, 0.96, 0.62, 1)
RED = (1.0, 0.53, 0.55, 1)
DIM = (0.49, 0.68, 0.78, 1)


class NeonGlyph(Widget):
    """A real 24-unit line-art pictogram, rescaled with its Kivy widget."""

    def __init__(self, icon, *, tint=CYAN, edge=26, **kwargs):
        self.icon = icon
        self.tint = tint
        super().__init__(size_hint=(None, None),
                         size=(dp(edge), dp(edge)), **kwargs)
        self.bind(pos=self._paint, size=self._paint)
        self._paint()

    def set_tint(self, tint):
        if self.tint != tint:
            self.tint = tint
            self._paint()

    def _paint(self, *_):
        self.canvas.before.clear()
        scale = min(self.width, self.height) / 24.0
        x0 = self.center_x - scale * 12
        y0 = self.center_y - scale * 12

        def p(x, y):
            return (x0 + x * scale, y0 + y * scale)

        def stroke(*coords, close=False, width=1.8):
            xy = []
            for px, py in coords:
                xy.extend(p(px, py))
            Line(points=xy, close=close, width=dp(width),
                 cap="round", joint="round")

        def oval(x, y, w, h, *, filled=False):
            x1, y1 = p(x, y)
            if filled:
                Ellipse(pos=(x1, y1), size=(w * scale, h * scale))
            else:
                Line(ellipse=(x1, y1, w * scale, h * scale),
                     width=dp(1.7))

        def polygon(points):
            stroke(*points, close=True)

        with self.canvas.before:
            Color(*self.tint)
            name = self.icon
            if name in ("cube", "package"):
                polygon(((12, 2), (21, 7), (21, 17), (12, 22),
                         (3, 17), (3, 7)))
                stroke((3, 7), (12, 12), (21, 7))
                stroke((12, 12), (12, 22))
                stroke((12, 12), (12, 2))
            elif name == "layers":
                for shift in (0, -5, -10):
                    stroke((3, 16 + shift), (12, 21 + shift),
                           (21, 16 + shift))
                    stroke((3, 16 + shift), (12, 11 + shift),
                           (21, 16 + shift))
            elif name == "database":
                oval(4, 16, 16, 6)
                stroke((4, 19), (4, 5))
                stroke((20, 19), (20, 5))
                stroke((4, 12), (7, 9.6), (12, 9),
                       (17, 9.6), (20, 12))
                stroke((4, 5), (7, 2.6), (12, 2),
                       (17, 2.6), (20, 5))
            elif name == "document":
                polygon(((5, 2), (19, 2), (19, 17),
                         (14, 22), (5, 22)))
                stroke((14, 22), (14, 17), (19, 17))
                stroke((8, 12), (16, 12))
                stroke((8, 8), (16, 8))
            elif name == "bundle":
                polygon(((12, 21), (16, 19), (16, 14),
                         (12, 12), (8, 14), (8, 19)))
                polygon(((5, 12), (9, 10), (9, 5),
                         (5, 3), (1, 5), (1, 10)))
                polygon(((19, 12), (23, 10), (23, 5),
                         (19, 3), (15, 5), (15, 10)))
                stroke((12, 12), (12, 8), (9, 8))
                stroke((12, 8), (15, 8))
            elif name in ("gear", "settings"):
                points = []
                for i in range(24):
                    angle = 2 * pi * i / 24
                    radius = 10 if i % 3 == 0 else 8
                    points.append((12 + radius * cos(angle),
                                   12 + radius * sin(angle)))
                polygon(points)
                oval(9, 9, 6, 6)
            elif name == "shield":
                polygon(((12, 2), (19, 6), (20, 18),
                         (12, 22), (4, 18), (5, 6)))
                stroke((8, 12), (11, 9), (17, 16), width=2.2)
            elif name in ("check", "check-circle"):
                if name == "check-circle":
                    oval(2, 2, 20, 20)
                stroke((6, 12), (10, 8), (18, 17), width=2.2)
            elif name == "pending":
                oval(2, 2, 20, 20)
            elif name == "error":
                oval(2, 2, 20, 20)
                stroke((12, 8), (12, 17), width=2.2)
                oval(11.1, 4.2, 1.8, 1.8, filled=True)
            elif name == "info":
                oval(2, 2, 20, 20)
                stroke((12, 7), (12, 14))
                oval(11.2, 17, 1.6, 1.6, filled=True)
            elif name == "pulse":
                stroke((1, 12), (5, 12), (8, 17), (11, 5),
                       (14, 15), (17, 12), (23, 12))
            elif name == "play":
                polygon(((7, 3), (20, 12), (7, 21)))
            elif name == "refresh":
                Line(circle=(*p(12, 12), 8 * scale, 35, 305),
                     width=dp(2.3), cap="round")
                stroke((18, 19), (20, 18), (20, 13), width=2.3)
                stroke((4, 5), (4, 11), (6, 7), width=2.3)
            elif name == "wifi":
                for radius in (10, 6):
                    Line(circle=(*p(12, 9), radius * scale, 42, 138),
                         width=dp(1.9), cap="round")
                oval(11, 6, 2, 2, filled=True)
            elif name == "arrow":
                stroke((5, 5), (12, 12), (5, 19))
                stroke((12, 5), (19, 12), (12, 19))
            else:
                oval(3, 3, 18, 18)


class VerificationRail(Widget):
    """Seven aligned live-state checkpoints with a single connecting trace."""

    def __init__(self, **kwargs):
        self.states = ("pending",) * 7
        super().__init__(size_hint_x=None, width=dp(24), **kwargs)
        self.bind(pos=self._paint, size=self._paint)
        self._paint()

    def set_states(self, states):
        next_states = tuple(states)
        if next_states != self.states:
            self.states = next_states
            self._paint()

    def _paint(self, *_):
        self.canvas.before.clear()
        row_height, gap = dp(37), dp(4)
        ys = [self.top - row_height / 2 - i * (row_height + gap)
              for i in range(7)]
        x = self.center_x
        with self.canvas.before:
            Color(.24, .93, .99, .54)
            Line(points=(x, ys[0], x, ys[-1]), width=dp(1.6))
            for y, status in zip(ys, self.states):
                tint = GREEN if status == "passed" else (
                    RED if status == "blocked" else CYAN)
                Color(*tint)
                Line(circle=(x, y, dp(6.4)), width=dp(1.8))
                if status == "passed":
                    Line(points=(x-dp(3), y, x-dp(.5), y-dp(2.5),
                                 x+dp(3.6), y+dp(3)),
                         width=dp(1.8), cap="round", joint="round")
                elif status == "checking":
                    Ellipse(pos=(x-dp(2), y-dp(2)),
                            size=(dp(4), dp(4)))
                elif status == "blocked":
                    Line(points=(x, y-dp(3), x, y+dp(3)),
                         width=dp(1.7))
