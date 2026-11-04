"""Dependency-free contracts for the compact login and secret visibility.

Compile the production methods directly so credential lifecycle regressions
are tested without importing a window provider or opening a network session.
"""
import ast
import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


SOURCE = (Path(__file__).resolve().parents[1] / 'android_app/app.py').read_text()
TREE = ast.parse(SOURCE)
APP = next(node for node in TREE.body if isinstance(node, ast.ClassDef)
           and node.name == 'LaLaApp')


def production_app(**globals_):
    names = {'_mask_password', 'toggle_password_visibility', 'switch_saved',
             'saved_names', 'connect_account', 'delete_saved', 'on_pause', 'on_stop'}
    methods = [node for node in APP.body
               if isinstance(node, ast.FunctionDef) and node.name in names]
    tree = ast.Module(body=[ast.ClassDef(name='Subject', bases=[], keywords=[],
                                       body=methods, decorator_list=[])], type_ignores=[])
    namespace = {'platform': 'linux', **globals_}
    exec(compile(ast.fix_missing_locations(tree), '<production-login>', 'exec'), namespace)
    namespace['LaLaApp'] = namespace['Subject']
    app = namespace['Subject']()
    app.password = SimpleNamespace(text='secret', password=True)
    app.password_toggle = SimpleNamespace(text='顯示')
    app.account = SimpleNamespace(text='player')
    app.server = SimpleNamespace(text='S1')
    app.message = SimpleNamespace(text='')
    app.remember = SimpleNamespace(active=False)
    app.catalog_sync = None
    app.vault = None
    app.saved_accounts = []
    app.lookup = {'S1': {'host': 'example.invalid', 'port': 1}}
    app.manager = SimpleNamespace(background=True, start=Mock(return_value=None),
                                  stop_all=Mock(), set_paused=Mock())
    return app


class PasswordVisibilityTests(unittest.TestCase):
    def test_repeated_toggle_preserves_secret_and_tracks_label(self):
        app = production_app()
        for _ in range(3):
            app.toggle_password_visibility()
            self.assertFalse(app.password.password)
            self.assertEqual(app.password_toggle.text, '隱藏')
            app.toggle_password_visibility()
            self.assertTrue(app.password.password)
            self.assertEqual(app.password_toggle.text, '顯示')
        self.assertEqual(app.password.text, 'secret')

    def test_pause_clears_and_masks_without_stopping_background_session(self):
        app = production_app()
        app.toggle_password_visibility()
        self.assertTrue(app.on_pause())
        self.assertEqual(app.password.text, '')
        self.assertTrue(app.password.password)
        self.assertEqual(app.password_toggle.text, '顯示')
        app.manager.set_paused.assert_called_once_with(True)
        app.manager.stop_all.assert_not_called()

    def test_stop_clears_and_masks(self):
        app = production_app()
        app.toggle_password_visibility()
        app.on_stop()
        self.assertEqual(app.password.text, '')
        self.assertTrue(app.password.password)

    def test_switch_account_masks_newly_loaded_password(self):
        retrieve = Mock(return_value='new secret')
        app = production_app(saved_password=retrieve)
        app.vault = object()
        app.saved_accounts = [{'account': 'second', 'server': 'S2'}]
        app.toggle_password_visibility()
        app.switch_saved(None, 'second | S2')
        self.assertEqual(app.account.text, 'second')
        self.assertEqual(app.server.text, 'S2')
        self.assertEqual(app.password.text, 'new secret')
        self.assertTrue(app.password.password)
        self.assertEqual(app.password_toggle.text, '顯示')
        retrieve.assert_called_once_with(app.vault, 'S2', 'second')

    def test_switch_failure_does_not_retain_visible_secret(self):
        app = production_app(saved_password=Mock(side_effect=ValueError))
        app.vault = object()
        app.saved_accounts = [{'account': 'second', 'server': 'S2'}]
        app.toggle_password_visibility()
        app.switch_saved(None, 'second | S2')
        self.assertEqual(app.password.text, '')
        self.assertTrue(app.password.password)

    def test_connect_clears_masks_and_passes_unchanged_credentials(self):
        app = production_app()
        app.toggle_password_visibility()
        app.connect_account()
        self.assertTrue(app.password.password)
        self.assertEqual(app.password.text, '')
        app.manager.start.assert_called_once_with(label='S1', host='example.invalid',
                                                  port=1, account='player', password='secret')

    def test_failed_validation_also_masks_without_starting_session(self):
        app = production_app()
        app.account.text = ''
        app.toggle_password_visibility()
        app.connect_account()
        self.assertTrue(app.password.password)
        app.manager.start.assert_not_called()

    def test_android_gate_still_prevents_connection(self):
        app = production_app(platform='android')
        app._login_visible = False
        app.toggle_password_visibility()
        app.connect_account()
        self.assertTrue(app.password.password)
        app.manager.start.assert_not_called()

    def test_delete_masks_and_clears_before_next_password_entry(self):
        remove = Mock(return_value=[])
        app = production_app(delete_account=remove)
        app.vault = object()
        app.saved_accounts = [{'account': 'player', 'server': 'S1'}]
        app.saved = SimpleNamespace(text='player | S1', values=['player | S1'])
        app.toggle_password_visibility()
        app.delete_saved()
        remove.assert_called_once_with(app.vault, 'S1', 'player')
        self.assertEqual(app.password.text, '')
        self.assertTrue(app.password.password)
        self.assertEqual(app.password_toggle.text, '顯示')
        app.password.text = 'next secret'
        self.assertTrue(app.password.password)

    def test_delete_failure_masks_and_preserves_saved_record(self):
        app = production_app(delete_account=Mock(side_effect=ValueError))
        app.vault = object()
        app.saved_accounts = [{'account': 'player', 'server': 'S1'}]
        app.saved = SimpleNamespace(text='player | S1')
        app.toggle_password_visibility()
        app.delete_saved()
        self.assertTrue(app.password.password)
        self.assertEqual(len(app.saved_accounts), 1)

    def test_mask_before_widgets_exist_is_safe(self):
        app = production_app()
        del app.password
        del app.password_toggle
        app._mask_password()


class CompactLoginSourceTests(unittest.TestCase):
    def setUp(self):
        method = next(node for node in APP.body
                      if isinstance(node, ast.FunctionDef) and node.name == '_build_login_view')
        self.source = ast.get_source_segment(SOURCE, method)

    def test_fields_are_horizontal_with_short_fixed_labels(self):
        for title, control in [('分流', 'self.server'), ('帳號', 'self.account')]:
            self.assertIn(f"field_row('{title}', {control})", self.source)
        self.assertIn("field_row('密碼', row(self.password, self.password_toggle))", self.source)
        self.assertIn('caption.width = dp(40)', self.source)
        self.assertIn('self.password_toggle.width = dp(48)', self.source)

    def test_saved_accounts_follow_credentials_and_stay_touch_sized(self):
        self.assertLess(self.source.index('self.password ='), self.source.index('self.saved ='))
        self.assertIn('login.add_widget(row(self.saved, delete))', self.source)
        self.assertIn('delete.width = dp(48)', self.source)
        self.assertIn('password=True', self.source)

    def test_no_mock_sessions_or_dead_bottom_navigation(self):
        self.assertNotIn('BottomNav', self.source)
        self.assertNotIn('lalaplayer01', self.source)
        self.assertIn("button('啟動／重新連接背景服務', self.initialize_android)", self.source)


HAS_DISPLAY = (os.environ.get('DISPLAY') or os.name == 'nt'
               or os.environ.get('SDL_VIDEODRIVER') == 'offscreen')


@unittest.skipUnless(importlib.util.find_spec('kivy') and HAS_DISPLAY,
                     'Requires Kivy and a display or SDL offscreen driver')
class CompactLoginWidgetTests(unittest.TestCase):
    def test_narrow_form_bounds_order_and_toggle_callback(self):
        # Keep the real widget tree, but do not import the game-session stack:
        # its module-level data loads require a separately installed runtime.
        tree = ast.parse(SOURCE)
        tree.body = [node for node in tree.body if not (
            isinstance(node, ast.ImportFrom) and node.module == 'android_app.sessions')]
        namespace = {
            '__file__': str(Path(__file__).resolve().parents[1] / 'android_app/app.py'),
            'SessionManager': lambda: None,
        }
        exec(compile(tree, '<production-login-widgets>', 'exec'), namespace)
        LaLaApp = namespace['LaLaApp']
        from kivy.clock import Clock
        from kivy.core.window import Window
        from kivy.metrics import dp

        app = LaLaApp()
        app.drain_events = lambda *_: None
        with patch('wlre.storage.server_lines.load', return_value=[]):
            root = app._build_login_view()
        self.addCleanup(app._drain_timer.cancel)
        previous_size = Window.size
        self.addCleanup(setattr, Window, 'size', previous_size)
        Window.size = (dp(320), dp(800))
        Window.add_widget(root)
        self.addCleanup(Window.remove_widget, root)
        for _ in range(12):
            Clock.tick()
        for name in ('server', 'account', 'password', 'password_toggle', 'saved'):
            control = getattr(app, name)
            with self.subTest(control=name):
                self.assertGreaterEqual(control.x, 0)
                self.assertLessEqual(control.right, dp(320))
                self.assertGreaterEqual(control.height, dp(48))
        self.assertGreaterEqual(app.password.width, dp(160))
        self.assertGreater(app.password.y, app.saved.y)
        self.assertTrue(app.password.password)
        app.password_toggle.dispatch('on_release')
        self.assertFalse(app.password.password)
        app.password_toggle.dispatch('on_release')
        self.assertTrue(app.password.password)
        self.assertTrue(app.remember.disabled)
        self.assertEqual(app.server.text, '沒有伺服器')

        # Moving the action into the login card must not add another service
        # start, and rebuilding must replace rather than stack drain timers.
        previous_timer = app._drain_timer
        app.initialize_android = Mock()
        namespace['platform'] = 'android'
        rebuilt = app._build_login_view()
        self.addCleanup(app._drain_timer.cancel)
        self.assertFalse(previous_timer.is_triggered)
        app.initialize_android.assert_not_called()
        restart_buttons = [widget for widget in rebuilt.walk()
                           if getattr(widget, 'text', '') == '啟動／重新連接背景服務']
        self.assertEqual(len(restart_buttons), 1)
        restart_buttons[0].dispatch('on_release')
        app.initialize_android.assert_called_once_with()


if __name__ == '__main__':
    unittest.main()
