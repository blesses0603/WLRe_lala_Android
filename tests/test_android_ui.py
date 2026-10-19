import importlib.util
import os
import unittest
from unittest.mock import patch

HAS_KIVY = importlib.util.find_spec('kivy') is not None


@unittest.skipUnless(HAS_KIVY and (os.environ.get('DISPLAY') or os.name == 'nt'),
                     'Requires Kivy and a desktop display')
class AndroidUI(unittest.TestCase):
    def setUp(self):
        from android_app.app import LaLaApp
        from android_app.sessions import Session
        from kivy.clock import Clock
        self.app = LaLaApp(); self.root = self.app.build()
        self.addCleanup(lambda: Clock.unschedule(self.app.drain_events))
        self.session = Session('fixture', 'fixture', 'fixture-user', 'fixture.invalid', 1234)
        self.session.phase = 'role_selection'
        self.session.roles = [dict(index=1, name='測試', level=14, locked=False),
                              dict(index=2, name='鎖定', level=10, locked=True)]
        self.app.manager.sessions['fixture'] = self.session
        self.app.account.text = 'fixture-user'; self.app.password.text = 'fixture-secret'
        with patch.object(self.app.manager, 'start', return_value=self.session):
            self.app.connect_account()
        self.status, self.buttons, _, self.stop, _ = self.app.cards['fixture']

    def roles(self):
        self.app.manager.events.put(('fixture', 'roles', self.session.roles))
        self.app.drain_events()

    def test_round_theme_styles_buttons_inputs_selectors_cards_and_checks(self):
        from kivy.uix.button import Button
        from kivy.uix.textinput import TextInput
        from android_app.theme import (
            ACCENT, SOFT, PRIMARY_FILL, style_button, style_input, surface)
        from android_app.widgets import RoundedSpinnerOption, column, select, check

        control = style_button(Button(text='測試'))
        self.assertTrue(hasattr(control, '_lala_button_colors'))
        self.assertEqual(tuple(control.background_color), (0, 0, 0, 0))
        for actual, expected in zip(control._lala_button_colors[1].rgba, SOFT):
            self.assertAlmostEqual(actual, expected, places=5)
        first_fill = control._lala_button_colors[1]
        style_button(control, primary=True)
        self.assertIs(control._lala_button_colors[1], first_fill)
        for actual, expected in zip(first_fill.rgba, PRIMARY_FILL):
            self.assertAlmostEqual(actual, expected, places=5)
        control.state = 'down'
        self.assertNotEqual(tuple(first_fill.rgba), PRIMARY_FILL)
        control.state = 'normal'
        control.disabled = True
        self.assertNotEqual(tuple(first_fill.rgba), PRIMARY_FILL)

        entry = style_input(TextInput(multiline=False))
        self.assertTrue(hasattr(entry, '_lala_input_colors'))
        self.assertEqual(tuple(entry.background_color), (0, 0, 0, 0))
        box = surface(column())
        self.assertTrue(hasattr(box, '_lala_surface_colors'))
        spinner = select(box, '分流', ['地球', '水星'])
        self.assertIs(spinner.option_cls, RoundedSpinnerOption)
        self.assertTrue(hasattr(RoundedSpinnerOption(text='地球'), '_lala_button_colors'))
        toggle = check(box, '保存帳號')
        self.assertTrue(hasattr(toggle, '_lala_check_parts'))
        toggle.active = True
        for actual, expected in zip(toggle._lala_check_parts[4].rgba, ACCENT):
            self.assertAlmostEqual(actual, expected, places=5)
        self.assertTrue(hasattr(self.app.remember, '_lala_check_parts'))

    def test_input_text_has_accessible_contrast_in_focus_and_normal_state(self):
        from kivy.uix.textinput import TextInput
        from android_app.theme import (
            INPUT_FILL, FOCUS_FILL, INPUT_TEXT, INPUT_HINT, INPUT_CARET,
            style_input,
        )

        def luminance(rgb):
            channels = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
                        for v in rgb[:3]]
            return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]

        def contrast(first, second):
            high, low = sorted((luminance(first), luminance(second)), reverse=True)
            return (high + 0.05) / (low + 0.05)

        for background in (INPUT_FILL, FOCUS_FILL):
            self.assertGreaterEqual(contrast(INPUT_TEXT, background), 7.0)
            self.assertGreaterEqual(contrast(INPUT_HINT, background), 4.5)

        entry = style_input(TextInput(text='中文測試 123', multiline=False))
        self.assertEqual(entry.text, '中文測試 123')
        for property_name, expected in (
            ('foreground_color', INPUT_TEXT),
            ('disabled_foreground_color', INPUT_HINT),
            ('hint_text_color', INPUT_HINT),
            ('cursor_color', INPUT_CARET),
        ):
            for actual, target in zip(getattr(entry, property_name), expected):
                self.assertAlmostEqual(actual, target, places=5)
        for actual, target in zip(entry._lala_input_colors[1].rgba, INPUT_FILL):
            self.assertAlmostEqual(actual, target, places=5)
        entry.focus = True
        for actual, target in zip(entry._lala_input_colors[1].rgba, FOCUS_FILL):
            self.assertAlmostEqual(actual, target, places=5)
        for input_widget in (entry, self.app.account, self.app.password):
            for actual, target in zip(input_widget.foreground_color, INPUT_TEXT):
                self.assertAlmostEqual(actual, target, places=5)

    def test_input_round_background_is_beneath_hints_and_rendered_text(self):
        from kivy.uix.textinput import TextInput
        from kivy.clock import Clock
        from android_app.theme import INPUT_FONT, style_input

        # The reported phone bug: both the hint and input glyphs disappear
        # despite good foreground/background contrast. This is a draw-order
        # regression, not a color-contrast failure.
        field = style_input(TextInput(hint_text='輸入帳號', multiline=False))
        backdrop = field._lala_input_background_group
        self.assertIs(field.canvas.before.children[0], backdrop)
        self.assertEqual(field.font_name, INPUT_FONT)
        self.assertEqual(field.hint_text, '輸入帳號')
        from android_app.theme import INPUT_HINT, INPUT_TEXT
        for actual, expected in zip(field._lala_input_glyph_color.rgba, INPUT_HINT):
            self.assertAlmostEqual(actual, expected, places=5)
        field.size = (320, 52)
        # A detached, unfocused Kivy TextInput deliberately ignores
        # insert_text(); set its value just as saved-account autofill does.
        field.text = 'abc中文'
        self.assertEqual(field.text, 'abc中文')
        for actual, expected in zip(field._lala_input_glyph_color.rgba, INPUT_TEXT):
            self.assertAlmostEqual(actual, expected, places=5)
        for _ in range(4):
            Clock.tick()
        self.assertIs(field.canvas.before.children[0], backdrop)
        self.assertTrue(any(texture for texture in field._lines_labels))

        # Password glyphs must be masked instead of omitted by the custom
        # canvas; the unmasked secret is retained only in TextInput.text.
        password = style_input(TextInput(
            hint_text='輸入密碼', password=True, multiline=False))
        self.assertIs(password.canvas.before.children[0],
                      password._lala_input_background_group)
        password.text = 'pass123'
        self.assertEqual(password.text, 'pass123')
        self.assertEqual(password.font_name, INPUT_FONT)
        for actual, expected in zip(password._lala_input_glyph_color.rgba, INPUT_TEXT):
            self.assertAlmostEqual(actual, expected, places=5)
        field.disabled = True
        for actual, expected in zip(
                field._lala_input_glyph_color.rgba, field.disabled_foreground_color):
            self.assertAlmostEqual(actual, expected, places=5)
        self.assertIs(self.app.account.canvas.before.children[0],
                      self.app.account._lala_input_background_group)
        self.assertIs(self.app.password.canvas.before.children[0],
                      self.app.password._lala_input_background_group)

    def test_chinese_font_is_used_and_has_distinct_glyphs(self):
        from kivy.core.text import Label
        from PIL import ImageFont
        label = Label(text='帳號'); label.resolve_font_name()
        font = ImageFont.truetype(label.options['font_name_r'], 32)
        self.assertNotEqual(bytes(font.getmask('帳')), bytes(font.getmask('號')))

    def test_narrow_phone_uses_one_scroll_and_card_grows_with_text(self):
        from kivy.clock import Clock
        from kivy.uix.scrollview import ScrollView
        self.root.size = (320, 640)
        for _ in range(8): Clock.tick()
        self.assertEqual(sum(isinstance(w, ScrollView) for w in self.root.walk()), 1)
        card = self.app.cards['fixture'][4]
        original_height = card.height
        self.status.text = '角色資訊與連線狀態測試 ' * 40
        for _ in range(8): Clock.tick()
        self.assertGreater(card.height, original_height)
        self.assertGreaterEqual(self.status.height, self.status.texture_size[1])
        for child in card.children:
            self.assertGreaterEqual(child.x, card.x)
            self.assertLessEqual(child.right, card.right + 1)
        self.assertEqual(self.app.empty_state.height, 0)
        self.session.active = False
        self.app.remove_card('fixture')
        for _ in range(4): Clock.tick()
        self.assertGreater(self.app.empty_state.height, 0)

    def test_locked_roles_and_pending_selection_stay_disabled(self):
        self.roles()
        self.assertFalse(self.buttons[1].disabled); self.assertTrue(self.buttons[2].disabled)
        self.app.choose_role('fixture', 1)
        self.assertTrue(all(button.disabled for button in self.buttons.values()))
        self.roles()
        self.assertTrue(all(button.disabled for button in self.buttons.values()))

    def test_finished_preserves_failure_and_allows_removal(self):
        self.session.active = False
        self.app.manager.events.put(('fixture', 'finished', '帳號驗證未通過'))
        self.app.drain_events()
        self.assertIn('帳號驗證未通過', self.status.text)
        self.assertTrue(all(button.disabled for button in self.buttons.values()))
        self.assertEqual(self.stop.text, '移除')
        self.app.remove_card('fixture')
        self.assertFalse(self.app.cards); self.assertFalse(self.app.manager.sessions)

    def test_snapshot_displays_hp_and_zero_sp_without_inventing_position(self):
        self.app.manager.events.put(('fixture', 'snapshot', dict(phase='world_ready', character='測試',
            level=14, hp=20, max_hp=50, sp=0, max_sp=30, scene=60000, position=None)))
        self.app.drain_events()
        self.assertIn('HP 20/50', self.status.text)
        self.assertIn('SP 0/30', self.status.text)
        self.assertIn('位置待同步', self.status.text)

    def test_resume_restores_visible_ui_and_existing_service_sessions(self):
        from kivy.core.window import Window
        from kivy.clock import Clock
        self.app.root = self.root
        Window.add_widget(self.root)
        self.addCleanup(lambda: Window.remove_widget(self.app.root)
                        if self.app.root in Window.children else None)
        self.addCleanup(lambda: Clock.unschedule(self.app._restore_foreground_ui))
        self.app._ui_started = True
        self.app.manager.background = True
        self.app.manager.available = True
        self.app.manager.metrics = {}
        self.app.account.text = 'preserved-user'
        self.app.password.text = 'must-not-survive'
        old_root = self.app.root
        self.assertTrue(self.app.on_pause())
        self.app.on_resume()
        Clock.unschedule(self.app._restore_foreground_ui)
        self.app._restore_foreground_ui()

        self.assertIsNot(self.app.root, old_root)
        self.assertIn(self.app.root, Window.children)
        self.assertNotIn(old_root, Window.children)
        self.assertEqual(self.app.account.text, 'preserved-user')
        self.assertEqual(self.app.password.text, '')
        self.assertIn('fixture', self.app.cards)
        self.assertIs(self.app.manager.sessions['fixture'], self.session)
        self.assertFalse(self.session.stop_event.is_set())
        self.assertIsNotNone(self.app._drain_timer)

    def test_resume_reattaches_ui_after_window_lost_root(self):
        from kivy.core.window import Window
        from kivy.clock import Clock
        self.app.root = self.root
        Window.add_widget(self.root)
        self.addCleanup(lambda: Window.remove_widget(self.app.root)
                        if self.app.root in Window.children else None)
        self.app._ui_started = True
        self.app.manager.background = True
        self.app.manager.available = True
        self.app.manager.metrics = {}
        Window.remove_widget(self.root)
        self.app.on_resume()
        Clock.unschedule(self.app._restore_foreground_ui)
        self.app._restore_foreground_ui()
        self.assertIn(self.app.root, Window.children)
        self.assertIsNot(self.app.root, self.root)
        self.assertEqual(len(self.app.cards), 1)
        self.assertFalse(self.session.stop_event.is_set())

    def test_pause_clears_password_and_prevents_late_role_enable(self):
        self.app.password.text = 'not-persisted'
        self.assertTrue(self.app.on_pause())
        self.assertEqual(self.app.password.text, '')
        self.assertTrue(self.session.stop_event.is_set())
        self.roles()
        self.assertTrue(all(button.disabled for button in self.buttons.values()))

    def test_android_pause_keeps_service_sessions(self):
        self.app.manager.background = True
        self.app.password.text = 'temporary'
        self.assertTrue(self.app.on_pause())
        self.app.on_stop()
        self.assertEqual(self.app.password.text, '')
        self.assertFalse(self.session.stop_event.is_set())

    def test_switch_and_delete_saved_account_preserves_other_account(self):
        records = [dict(server=self.app.server.text, account=name, password=name + '-secret')
                   for name in ('A', 'B')]
        class Vault:
            def __init__(self):
                self.records = [dict(record) for record in records]
            def load(self):
                return [dict(record) for record in self.records]
            def save(self, value):
                self.records = [dict(record) for record in value]
        self.app.vault = Vault()
        from android_app.credentials import public_accounts
        self.app.saved_accounts = public_accounts(records)
        self.app.saved.values = self.app.saved_names()
        self.app.saved.text = self.app.saved_names()[0]
        self.assertEqual(self.app.account.text, 'A')
        self.assertEqual(self.app.password.text, 'A-secret')
        self.assertTrue(all('password' not in r for r in self.app.saved_accounts))
        self.app.delete_saved()
        self.assertEqual([r['account'] for r in self.app.vault.records], ['B'])
        self.assertEqual(self.app.password.text, '')
        self.assertFalse(self.session.stop_event.is_set())

    def test_android_startup_error_keeps_ui_and_hides_exception_details(self):
        from types import SimpleNamespace
        import android_app.app as module
        def fail(_name): raise RuntimeError('fixture-secret must not appear')
        with patch.object(module, 'platform', 'android'), patch.dict('sys.modules', {'jnius': SimpleNamespace(autoclass=fail)}):
            self.app.initialize_android()
            self.assertIn('A01', self.app.message.text)
            self.assertNotIn('fixture-secret', self.app.message.text)
            with patch.object(self.app.manager, 'start') as start:
                self.app.connect_account()
                start.assert_not_called()
        self.assertIsNotNone(self.app.root if self.app.root else self.root)

    def test_monitor_failure_does_not_exit_render_loop(self):
        from types import SimpleNamespace
        import queue
        self.app.manager = SimpleNamespace(background=True, sessions={'fixture': self.session},
            available=True, metrics={'active': 1}, events=queue.Queue())
        with patch.object(self.app, 'render_metrics', side_effect=RuntimeError('private detail')):
            self.assertTrue(self.app.drain_events())
        self.assertIn('A06', self.app.resources.text)
        self.assertNotIn('private detail', self.app.resources.text)

    def test_automation_controls_follow_core_and_do_not_optimistically_enable(self):
        from android_app.automation_ui import refresh, toggle
        card = self.app.cards['fixture'][4]
        refresh(self.app, 'fixture')
        self.assertTrue(card.automation_buttons['battle'].disabled)
        self.session.phase = 'world_ready'
        refresh(self.app, 'fixture')
        self.assertFalse(card.automation_buttons['battle'].disabled)
        toggle(self.app, 'fixture', 'battle')
        self.assertEqual(card.automation_buttons['battle'].text, '處理中')
        self.assertFalse(self.session.automation.get('battle', {}).get('enabled', False))
        self.session.automation_pending.clear()
        self.session.automation = {'battle': {'enabled': True, 'status': 'armed'}}
        refresh(self.app, 'fixture')
        self.assertEqual(card.automation_buttons['battle'].text, '停止戰鬥')
        self.assertIn('AI待命', card.automation_status.text)
        self.session.active = False
        refresh(self.app, 'fixture')
        self.assertTrue(card.automation_buttons['battle'].disabled)

    def test_ai_dialog_saves_validated_preferences(self):
        from android_app.settings_ui import SettingsEditor
        from kivy.uix.checkbox import CheckBox
        with patch('android_app.widgets.Popup.open'):
            editor = SettingsEditor(self.app, 'fixture')
        checks = [w for w in editor.form.children if hasattr(w, 'children')]
        checkboxes = [w for w in editor.form.walk() if isinstance(w, CheckBox)]
        self.assertEqual(len(checkboxes), 3)
        checkboxes[0].active = True
        editor.save()
        self.assertTrue(self.session.ai_settings['bPlayerDieCloseAI'])
