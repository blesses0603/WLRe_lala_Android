"""Production-only game-style Kivy widgets.

These widgets render verified inventory, recipe and queue data. No generated
mock item names, result probabilities, server packets or gameplay commands
belong here. Static canvas paint keeps mobile CPU/GPU cost bounded.
"""
from kivy.metrics import dp
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget
from kivy.graphics import Color, RoundedRectangle

from android_app.assets import function_icon, item_image
from android_app.theme import (
    ACCENT, BORDER, DANGER, MUTED, SOFT, SURFACE, TEXT,
    neon_surface, surface, style_button, style_input,
)


def tiny_label(value='', *, height=26, font_size='12sp', color=TEXT):
    view = Label(
        text=str(value), color=color, font_size=font_size,
        size_hint_y=None, height=dp(height),
        halign='left', valign='middle', shorten=True)
    view.bind(size=lambda w, _: setattr(
        w, 'text_size', (max(0, w.width - dp(4)), w.height)))
    return view


def adaptive_text(value='', *, min_height=24, font_size='12sp', color=MUTED):
    """Wrap verified long status lines without reserving a blank 38dp row."""
    label = Label(
        text=str(value), color=color, font_size=font_size,
        size_hint_y=None, height=dp(min_height),
        halign='left', valign='middle')
    label.bind(width=lambda w, width: setattr(
        w, 'text_size', (max(0, width - dp(4)), None)))
    label.bind(texture_size=lambda w, size: setattr(
        w, 'height', max(dp(min_height), size[1] + dp(5))))
    return label


def action_button(title, callback, *, height=42, primary=False):
    view = Button(
        text=title, size_hint_y=None, height=dp(height), font_size='13sp',
        halign='center', valign='middle')
    style_button(view, primary=primary, radius=12)
    view.bind(on_release=lambda *_: callback())
    return view


class ProductionPanel(BoxLayout):
    """Only one bright outline per logical section; no nested page frame."""

    def __init__(self, heading, description='', icon_name=None, **kwargs):
        super().__init__(
            orientation='vertical', spacing=dp(5),
            padding=[dp(8), dp(6), dp(8), dp(7)],
            size_hint_y=None, **kwargs)
        self.bind(minimum_height=self.setter('height'))
        neon_surface(self, color=SURFACE, border=BORDER, radius=17)
        head = BoxLayout(
            orientation='horizontal', spacing=dp(7),
            size_hint_y=None, height=dp(31))
        icon = function_icon(icon_name, 26) if icon_name else None
        if icon is not None:
            head.add_widget(icon)
        title = tiny_label(heading, height=31, font_size='16sp')
        head.add_widget(title)
        self.heading = title
        self.add_widget(head)
        if description:
            note = tiny_label(
                description, height=19, font_size='10sp', color=MUTED)
            self.add_widget(note)


class AlchemyLevelBar(BoxLayout):
    """Maps visible beginner/mid/advanced names to verified core modes.

    The game's original command modes remain unchanged. Locked or unknown
    skills cannot be selected just because a mockup contains that button.
    """

    # Four visible grades replace mockup's unsupported three mode labels.
    # The left side must remain the real server/core mode string.
    LEVELS = (
        ('無技能', '無煉金術'),
        ('一般', '初級煉金術'),
        ('中階', '中級煉金術'),
        ('高階', '高級煉金術'),
    )

    def __init__(self, on_choose):
        super().__init__(
            orientation='horizontal', spacing=dp(5),
            size_hint_y=None, height=dp(42))
        self.buttons = {}
        for core_mode, display in self.LEVELS:
            control = action_button(
                display, lambda value=core_mode: on_choose(value),
                height=40)
            control.font_size = '11sp'
            self.buttons[core_mode] = control
            self.add_widget(control)
        self.set_available(('無技能',), '無技能')

    def set_available(self, allowed, selected):
        permitted = set(allowed)
        for value, control in self.buttons.items():
            control.disabled = value not in permitted
            style_button(
                control, primary=(value == selected and value in permitted),
                radius=12)
            # style_button normalizes typography; short labels must still
            # fit four columns on a 320dp phone.
            control.font_size = '10sp'


class MaterialSlot(BoxLayout):
    """Selectable source-backed icon, removable selection and live qty draft."""

    def __init__(self, slot_index, on_choose, on_remove,
                 icon_factory=None):
        super().__init__(
            orientation='vertical', spacing=dp(1),
            padding=[dp(3), dp(2), dp(3), dp(3)],
            size_hint_y=None, height=dp(132))
        self.slot_index = slot_index
        self.item_id = None
        self.icon_factory = icon_factory or (
            lambda sid: item_image(sid, size=36))
        neon_surface(self, color=SOFT, border=BORDER, radius=12)
        header = BoxLayout(
            orientation='horizontal', size_hint_y=None, height=dp(18))
        self.slot_label = tiny_label(
            '材料 {}'.format(slot_index + 1), height=18,
            font_size='10sp', color=MUTED)
        header.add_widget(self.slot_label)
        self.remove_button = action_button(
            '×', on_remove, height=18)
        self.remove_button.size_hint_x = None
        self.remove_button.width = dp(21)
        self.remove_button.disabled = True
        header.add_widget(self.remove_button)
        self.add_widget(header)

        self.icon_holder = AnchorLayout(
            anchor_x='center', anchor_y='center',
            size_hint_y=None, height=dp(30))
        self.add_widget(self.icon_holder)
        self.title = tiny_label(
            '未選取', height=17, font_size='10sp', color=MUTED)
        self.title.halign = 'center'
        self.add_widget(self.title)
        self.pick_button = action_button(
            '選取材料', on_choose, height=29)
        self.pick_button.font_size = '10sp'
        self.add_widget(self.pick_button)
        self.quantity = style_input(TextInput(
            text='1', multiline=False, input_filter='int',
            input_type='number', font_size='12sp',
            size_hint_y=None, height=dp(25)))
        self.quantity.padding = [dp(4), dp(2), dp(4), dp(2)]
        self.add_widget(self.quantity)
        self.set_item(None)

    def set_item(self, record, name=None):
        self.icon_holder.clear_widgets()
        if record is None:
            self.item_id = None
            self.title.text = '未選取'
            self.slot_label.text = '材料 {}'.format(self.slot_index + 1)
            self.remove_button.disabled = True
            self.icon_holder.add_widget(Label(
                text='+', color=ACCENT, font_size='21sp'))
        else:
            sid = record['item_id']
            self.item_id = sid
            self.title.text = name if name is not None else str(sid)
            self.slot_label.text = '格位 #{}'.format(record['index'])
            self.remove_button.disabled = False
            self.icon_holder.add_widget(self.icon_factory(sid))
        self.pick_button.text = (
            '格位 #{}'.format(record['index']) if record is not None
            else '材料 {}'.format(self.slot_index + 1))
        surface(self, color=SOFT,
                border=ACCENT if record is not None else BORDER, radius=12)


class RecipeRow(ButtonBehavior, BoxLayout):
    """One tap selects a verified catalog row. No implicit craft command."""

    def __init__(self, recipe, title, subtitle, on_select, favorite=False,
                 icon_factory=None):
        super().__init__(
            orientation='horizontal', size_hint_y=None,
            height=dp(57), spacing=dp(5),
            padding=[dp(5), dp(4), dp(5), dp(4)])
        self.item_id = recipe['item_id']
        surface(self, color=SOFT, border=BORDER, radius=12)
        sprite = (icon_factory(self.item_id) if icon_factory
                  else item_image(self.item_id, size=40))
        self.add_widget(sprite)
        texts = BoxLayout(orientation='vertical', spacing=dp(1))
        top = tiny_label(title, height=25, font_size='12sp')
        bottom = tiny_label(subtitle, height=18, font_size='10sp',
                            color=MUTED)
        texts.add_widget(top)
        texts.add_widget(bottom)
        self.add_widget(texts)
        if favorite:
            star = tiny_label('收藏', height=40, font_size='10sp',
                              color=ACCENT)
            star.size_hint_x = None
            star.width = dp(29)
            self.add_widget(star)
        self.bind(on_release=lambda *_: on_select(recipe))

    def set_selected(self, active):
        surface(self, color=(.02, .25, .32, .98) if active else SOFT,
                border=ACCENT if active else BORDER, radius=12)


class IngredientRow(BoxLayout):
    """Display only real material_rows values; unknown stock stays unknown."""

    def __init__(self, record, icon_factory=None):
        super().__init__(
            orientation='horizontal', size_hint_y=None,
            height=dp(33), spacing=dp(6))
        sid = record.get('item_id')
        if sid is not None:
            self.add_widget(
                icon_factory(sid) if icon_factory
                else item_image(sid, size=27))
        name = tiny_label(record['name'], height=31,
                          font_size='11sp')
        self.add_widget(name)
        count = record.get('usable')
        required = record['required']
        known = count is not None
        enough = known and count >= required
        status = tiny_label(
            '{}/{}'.format(count, required) if known else '待同步',
            height=31, font_size='11sp',
            color=ACCENT if enough else (DANGER if known else MUTED))
        status.size_hint_x = None
        status.width = dp(72)
        status.halign = 'right'
        self.add_widget(status)


class ProgressRail(Widget):
    """Visible only from confirmed progress; no invented percentage."""

    def __init__(self, **kwargs):
        super().__init__(size_hint_y=None, height=dp(7), **kwargs)
        self.ratio = 0
        with self.canvas.before:
            Color(.06, .19, .29, .97)
            self.track = RoundedRectangle(radius=[dp(4)])
            Color(.25, .91, .97, 1)
            self.fill = RoundedRectangle(radius=[dp(4)])
        self.bind(pos=self._geometry, size=self._geometry)
        self._geometry()

    def set_ratio(self, ratio):
        self.ratio = max(0, min(1, float(ratio)))
        self._geometry()

    def _geometry(self, *_):
        self.track.pos = self.pos
        self.track.size = self.size
        self.fill.pos = self.pos
        self.fill.size = (self.width * self.ratio, self.height)


class QueueEntry(BoxLayout):
    """Two compact rows keep queue controls touchable on narrow Android."""

    def __init__(self, item_id, name, count, index, remaining,
                 progress, on_action, icon_factory=None):
        super().__init__(
            orientation='vertical', size_hint_y=None,
            height=dp(109), spacing=dp(5),
            padding=[dp(6), dp(4), dp(6), dp(4)])
        surface(self, color=SOFT, border=BORDER, radius=12)
        top = BoxLayout(
            orientation='horizontal', size_hint_y=None,
            spacing=dp(6), height=dp(39))
        top.add_widget(
            icon_factory(item_id) if icon_factory
            else item_image(item_id, size=36))
        info = tiny_label(
            '#{} {} ×{}'.format(index, name, count),
            height=38, font_size='12sp')
        top.add_widget(info)
        self.add_widget(top)
        status = BoxLayout(
            orientation='horizontal', size_hint_y=None,
            height=dp(15), spacing=dp(7))
        self.progress = ProgressRail()
        status.add_widget(self.progress)
        if progress is None:
            self.progress.set_ratio(0)
            remainder = '進度待同步'
        else:
            self.progress.set_ratio(progress)
            remainder = '剩餘 {}'.format(remaining)
        label = tiny_label(
            remainder, height=15, font_size='10sp', color=MUTED)
        label.size_hint_x = None
        label.width = dp(105)
        status.add_widget(label)
        self.add_widget(status)
        actions = BoxLayout(
            orientation='horizontal', size_hint_y=None,
            height=dp(35), spacing=dp(5))
        for title, action in (
                ('上移', 'up'), ('下移', 'down'), ('刪除', 'delete')):
            actions.add_widget(action_button(
                title, lambda a=action: on_action(a, index),
                height=35))
        self.add_widget(actions)
