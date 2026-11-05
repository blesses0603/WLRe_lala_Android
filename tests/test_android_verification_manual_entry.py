"""Reference-fidelity and explicit-entry contracts for the Android gate."""
import ast
import importlib.util
import os
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


def source(name):
    return (ROOT / name).read_text(encoding="utf-8")


class ManualEntryContracts(unittest.TestCase):
    def test_canvas_icons_are_real_and_not_font_symbols(self):
        icon_code = source("android_app/verification_icons.py")
        tree = ast.parse(icon_code)
        names = {node.name for node in tree.body if isinstance(node, ast.ClassDef)}
        self.assertIn("NeonGlyph", names)
        self.assertIn("VerificationRail", names)
        for name in ("cube", "layers", "database", "document", "bundle",
                     "gear", "shield", "check-circle", "refresh", "wifi", "play"):
            self.assertIn('"' + name + '"', icon_code)
        self.assertIn("Line(", icon_code)
        self.assertIn("Ellipse(", icon_code)
        self.assertNotIn("Clock.schedule_interval(", icon_code)

    def test_seven_live_icons_and_three_separate_actions(self):
        code = source("android_app/verification_ui.py")
        ast.parse(code)
        self.assertNotIn("VerificationRail", code)
        self.assertIn("step.update(view['steps'][key])", code)
        self.assertIn("self.rows[key]=item", code)
        self.assertIn("self.enter_login=NeonAction(", code)
        self.assertIn("self.enter_login.disabled=True", code)
        self.assertIn("self.enter_login.disabled = not view['approved']", code)
        self.assertIn("action_row.add_widget(self.retry)", code)
        self.assertIn("action_row.add_widget(self.service_button)", code)
        self.assertIn("inspection.add_widget(controls)", code)
        self.assertIn("controls.add_widget(self.enter_login)", code)
        self.assertNotIn("'◇','▤','▱','≡'", code)

    def test_gate_does_not_automatically_open_after_success(self):
        code = source("android_app/app.py")
        tree = ast.parse(code)
        klass = next(x for x in tree.body if isinstance(x, ast.ClassDef)
                     and x.name == "LaLaApp")
        functions = {node.name: node for node in klass.body
                     if isinstance(node, ast.FunctionDef)}
        self.assertIn("_enter_verified_login", functions)
        gate = ast.get_source_segment(code, functions["_update_verification_gate"])
        entry = ast.get_source_segment(code, functions["_enter_verified_login"])
        self.assertNotIn("_login_host.clear_widgets()", gate)
        self.assertNotIn("_login_visible = True", gate)
        self.assertIn("verified = self._login_ready()", gate)
        self.assertIn("login_ready=verified", gate)
        self.assertIn("if not self._login_ready():", entry)
        self.assertIn("_login_host.clear_widgets()", entry)
        self.assertIn("_login_visible = True", entry)
        self.assertIn("self._enter_verified_login)", code)

    def test_versions_stay_synced(self):
        import re
        app = re.search(r'ANDROID_VERSION = "([0-9.]+)"',
                        source('android_app/version.py'))
        spec = re.search(r'^version = ([0-9.]+)',
                         source('buildozer.spec'), flags=re.M)
        self.assertIsNotNone(app)
        self.assertIsNotNone(spec)
        self.assertEqual(app.group(1), spec.group(1))
        self.assertRegex(app.group(1), r'^[0-9]+[.][0-9]+[.][0-9]+')


HAS_KIVY = importlib.util.find_spec("kivy") is not None


@unittest.skipUnless(HAS_KIVY and (os.environ.get("DISPLAY") or os.name == "nt"),
                     "Requires Kivy and a desktop display")
class LiveDashboardContracts(unittest.TestCase):
    def test_user_entry_stays_disabled_until_verified(self):
        from android_app.verification_ui import VerificationDashboard
        calls = []
        panel = VerificationDashboard(
            lambda: calls.append("retry"),
            lambda: calls.append("service"),
            lambda: calls.append("enter"))
        self.assertTrue(panel.enter_login.disabled)
        self.assertEqual(len(panel.rows), 7)
        self.assertEqual(tuple(row._current for row in panel.rows.values()), ("pending",) * 7)
        token = [True, "a" * 64]
        worker = {"status": "ready", "ready": True, "catalog_token": token}
        phone = {"status": "ready", "ready": True, "catalog_token": token}
        panel.apply_state(worker, phone, connected=True, detail="已驗證",
                          login_ready=True)
        self.assertFalse(panel.enter_login.disabled)
        self.assertEqual(tuple(row._current for row in panel.rows.values()), ("passed",) * 7)
        panel.enter_login.dispatch("on_release")
        self.assertEqual(calls, ["enter"])
        panel.apply_state(worker, phone, connected=False, detail="失聯",
                          login_ready=True)
        self.assertTrue(panel.enter_login.disabled)
        self.assertNotEqual(tuple(row._current for row in panel.rows.values()), ("passed",) * 7)


if __name__ == "__main__":
    unittest.main()
