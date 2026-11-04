"""Pre-login validation is a visible screen gate, not only a disabled button."""
import importlib.util
import os
import queue
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from android_app.login_gate import verified_for_login

TOKEN = [True, "a" * 64]


def status(*, ready=True, state=None, token=None):
    return {"status": state or ("ready" if ready else "blocked"),
            "ready": ready, "catalog_token": list(TOKEN if token is None else token),
            "message": "官方版本、Runtime 與 SQLite 核對完成"}


class LoginGateRules(unittest.TestCase):
    def test_two_independent_verified_catalogs_enable_login(self):
        self.assertTrue(verified_for_login(status(), status(), connected=True))

    def test_versions_or_one_side_ready_never_enable_login(self):
        for service, local, connected in (
            (status(), status(), False),
            (status(ready=False), status(), True),
            (status(), status(ready=False), True),
            (status(state="checking"), status(), True),
            (status(), status(state="checking"), True),
            (status(), status(token=[True, "b" * 64]), True),
            (status(token=[False, "a" * 64]), status(), True),
            (status(token=[True, None]), status(), True),
            ({"ready": True}, status(), True),
            (status(), {"ready": True}, True),
            (None, status(), True),
        ):
            with self.subTest(service=service, local=local, connected=connected):
                self.assertFalse(verified_for_login(service, local, connected=connected))

    def test_untrusted_tokens_cannot_unlock_login(self):
        for token in (
            ["a" * 64], [True, "secret"], [True, "A" * 64],
            [True, "b" * 65], [True, "z" * 64], [1, "a" * 64], None,
        ):
            with self.subTest(token=token):
                self.assertFalse(verified_for_login(
                    status(token=token) if token is not None else
                    {"ready": True, "status": "ready", "catalog_token": None},
                    status(), connected=True))


HAS_KIVY = importlib.util.find_spec("kivy") is not None


@unittest.skipUnless(HAS_KIVY and (os.environ.get("DISPLAY") or os.name == "nt"),
                     "Requires Kivy and a desktop display")
class VisibleAndroidLoginGate(unittest.TestCase):
    def test_android_stays_on_gate_until_user_enters_after_double_check(self):
        import android_app.app as module
        from kivy.uix.textinput import TextInput
        from kivy.clock import Clock

        with patch.object(module, "platform", "android"):
            app = module.LaLaApp()
            root = app.build()
            self.addCleanup(app._drain_timer.cancel)
            self.assertFalse(app._login_visible)
            self.assertIn(app._verification_view, root.children)
            self.assertNotIn(app._login_view, root.children)
            self.assertFalse(any(isinstance(widget, TextInput) for widget in root.walk()))

            service = status(ready=False)
            local = status(ready=True)
            app.manager = SimpleNamespace(background=True, available=True,
                                          resource_status=service, sessions={},
                                          metrics={}, events=queue.Queue())
            app.catalog_sync = SimpleNamespace(snapshot=lambda: local)
            app._update_verification_gate()
            self.assertFalse(app._login_visible)
            self.assertTrue(app._verification_panel.enter_login.disabled)
            app._verification_panel.enter_login.dispatch('on_release')
            self.assertFalse(app._login_visible)
            self.assertIn(app._verification_view, root.children)

            service.update(status="ready", ready=True,
                           catalog_token=[True, "b" * 64])
            app._update_verification_gate()
            self.assertFalse(app._login_visible)
            self.assertIn(app._verification_view, root.children)

            service["catalog_token"] = list(TOKEN)
            app._update_verification_gate()
            self.assertFalse(app._login_visible)
            self.assertIn(app._verification_view, root.children)
            self.assertNotIn(app._login_view, root.children)
            self.assertFalse(app._verification_panel.enter_login.disabled)
            # User explicitly taps the new action at the previous service position.
            app._verification_panel.enter_login.dispatch("on_release")
            self.assertTrue(app._login_visible)
            self.assertIn(app._login_view, root.children)
            self.assertNotIn(app._verification_view, root.children)
            self.assertTrue(any(isinstance(widget, TextInput) for widget in root.walk()))
            Clock.unschedule(app.drain_events)

    def test_android_resume_rebuilds_gate_without_exposing_login_or_password(self):
        import android_app.app as module
        from kivy.core.window import Window
        from kivy.uix.textinput import TextInput

        with patch.object(module, "platform", "android"):
            app = module.LaLaApp()
            old = app.build()
            app.root = old
            Window.add_widget(old)
            def cleanup():
                app._drain_timer.cancel()
                if app.root in Window.children:
                    Window.remove_widget(app.root)
            self.addCleanup(cleanup)

            app._ui_started = True
            app.manager = SimpleNamespace(background=True, available=True,
                resource_status=status(ready=False), sessions={},
                metrics={}, events=queue.Queue())
            app.catalog_sync = SimpleNamespace(snapshot=lambda: status(ready=False))
            app.account.text = 'remember-user-not-password'
            app.password.text = 'PRIVATE-DO-NOT-RESTORE'
            app._restore_foreground_ui()

            self.assertIsNot(app.root, old)
            self.assertIn(app.root, Window.children)
            self.assertFalse(app._login_visible)
            self.assertFalse(any(isinstance(widget, TextInput)
                                 for widget in app.root.walk()))
            self.assertEqual(app.account.text, 'remember-user-not-password')
            self.assertEqual(app.password.text, '')

    def test_android_resource_failure_stays_on_gate_with_safe_retry(self):
        import android_app.app as module
        with patch.object(module, "platform", "android"):
            app = module.LaLaApp()
            root = app.build()
            self.addCleanup(app._drain_timer.cancel)
            app.manager = SimpleNamespace(background=True, available=True,
                resource_status={"status": "blocked", "ready": False,
                                 "message": "必要 Bundle 尚未下載"},
                sessions={}, metrics={}, events=queue.Queue())
            app.catalog_sync = SimpleNamespace(snapshot=lambda: status(ready=False))
            app._update_verification_gate()
            self.assertIn(app._verification_view, root.children)
            self.assertFalse(app._verification_retry.disabled)
            self.assertIn("必要 Bundle", app._verification_detail.text)
