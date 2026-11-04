"""Android verification page fidelity and fail-closed regression tests."""
import ast
import importlib.util
import os
from pathlib import Path
import unittest

from android_app.login_gate import verified_for_login
from android_app.resource_sync import ResourceSync, safe_display_receipt
from android_app.verification_presentation import STEPS, view_state

ROOT = Path(__file__).resolve().parents[1]
TOKEN = [True, "a" * 64]


def observed_result(*, failure=None):
    return {
        "remote": {
            "status": "same_resources",
            "checked_at_utc": "2026-11-04T00:40:21+00:00",
            "packages": {
                "DataPackage": {"remote": "1286_2026_11_04", "comparison": "same"},
                "MainPackage": {"remote": "1284_2026_11_04", "comparison": "same"},
            },
        },
        "runtime_failure": {"code": failure} if failure else None,
    }


class ModelTests(unittest.TestCase):
    def test_seven_rows_match_reference_and_have_descriptions(self):
        self.assertEqual([k for k, _, _ in STEPS],
                         ["official", "data", "main", "manifest",
                          "bundle", "runtime", "sqlite"])
        self.assertTrue(all(title and description for _, title, description in STEPS))

    def test_initial_and_offline_states_do_not_fake_success(self):
        result = view_state({}, {}, connected=False)
        self.assertFalse(result["approved"])
        self.assertTrue(all(status == "pending"
                            for status in result["steps"].values()))
        result = view_state({"status": "checking", "ready": False},
                            {}, connected=True)
        self.assertEqual(result["steps"]["official"], "checking")
        self.assertTrue(all(result["steps"][name] != "passed"
                            for name in ("manifest", "bundle", "sqlite")))

    def test_versions_only_from_validated_observed_remote(self):
        receipt = safe_display_receipt(observed_result(failure="manifest_download_failed"))
        self.assertEqual(receipt["verified_versions"],
                         {"DataPackage": "1286", "MainPackage": "1284"})
        self.assertEqual(receipt["failure_code"], "manifest_download_failed")
        self.assertEqual(receipt["checked_at_utc"],
                         "2026-11-04T00:40:21+00:00")
        view = view_state({"status": "blocked", **receipt}, {},
                          connected=True)
        self.assertEqual(view["steps"]["manifest"], "blocked")
        self.assertEqual(view["steps"]["data"], "passed")
        self.assertEqual(view["steps"]["sqlite"], "pending")
        self.assertFalse(view["approved"])

    def test_bad_untrusted_version_and_dates_never_enter_ui(self):
        report = observed_result(failure="../../secret")
        report["remote"]["packages"]["DataPackage"]["remote"] = "<script>1286"
        report["remote"]["packages"]["MainPackage"]["remote"] = "99999999999"
        report["remote"]["checked_at_utc"] = "PRIVATE /home/user"
        receipt = safe_display_receipt(report)
        self.assertEqual(receipt, {"verified_versions": {},
                                   "checked_at_utc": None,
                                   "failure_code": None})
        view = view_state({"verified_versions": {
            "DataPackage": "1286' OR '1'='1"}}, {}, connected=True)
        self.assertEqual(view["versions"], {})

    def test_trusted_worker_success_does_not_imply_phone_gate(self):
        service = {"status": "ready", "ready": True,
                   "catalog_token": TOKEN}
        local = {"status": "checking", "ready": False}
        view = view_state(service, local, connected=True, login_ready=True)
        self.assertFalse(view["approved"])
        self.assertEqual(view["steps"]["manifest"], "passed")
        self.assertEqual(view["steps"]["runtime"], "checking")
        self.assertEqual(view["steps"]["sqlite"], "pending")
        local = {"status": "blocked", "ready": False}
        view = view_state(service, local, connected=True, login_ready=True)
        self.assertFalse(view["approved"])
        self.assertEqual(view["steps"]["runtime"], "pending")
        self.assertEqual(view["steps"]["sqlite"], "pending")

    def test_all_green_only_after_real_matching_catalog_identity(self):
        service = {"status": "ready", "ready": True,
                   "catalog_token": TOKEN}
        local = {"status": "ready", "ready": True,
                 "catalog_token": TOKEN}
        self.assertTrue(verified_for_login(service, local, connected=True))
        view = view_state(service, local, connected=True, login_ready=True)
        self.assertTrue(view["approved"])
        self.assertTrue(all(v == "passed" for v in view["steps"].values()))
        view = view_state(service, dict(local, catalog_token=[True, "b"*64]),
                          connected=True, login_ready=True)
        self.assertFalse(view["approved"])
        self.assertNotEqual(view["steps"]["sqlite"], "passed")

    def test_resource_start_and_reset_clear_stale_receipts(self):
        sync = ResourceSync(download=False, checker=lambda: {})
        # Do not use a real worker or connect to any official server.
        sync.value.update(verified_versions={"DataPackage": "1286"},
                          checked_at_utc="2026-11-04T00:40:21Z",
                          failure_code="manifest_download_failed")
        self.assertTrue(sync.reset())
        state = sync.snapshot()
        self.assertEqual(state["verified_versions"], {})
        self.assertIsNone(state["failure_code"])
        self.assertIsNone(state["checked_at_utc"])

    def test_screen_is_real_kivy_controls_not_embedded_screenshot(self):
        path = ROOT / "android_app/verification_ui.py"
        code = path.read_text(encoding="utf-8")
        ast.parse(code, filename=str(path))
        self.assertIn("class VerificationDashboard(BoxLayout)", code)
        self.assertIn("class CosmicHeader(FloatLayout)", code)
        self.assertIn("class CheckRow(BoxLayout)", code)
        self.assertIn("class NeonAction(Button)", code)
        self.assertIn("self.scroller=ScrollView(", code)
        self.assertIn("self.rows[key]=item", code)
        self.assertIn("self.version_labels[name]=value", code)
        self.assertNotIn("DataPackage 1286", code)
        self.assertNotIn("所有項目驗證通過", code)
        self.assertNotIn("verify=False", code)
        self.assertNotIn("Clock.schedule_interval", code)

    def test_artwork_is_decorative_only_and_small(self):
        import struct
        for name in ("verification_mascot.jpg", "verification_castle.jpg"):
            path = ROOT / "android_app/assets" / name
            self.assertTrue(path.is_file(), name)
            self.assertLess(path.stat().st_size, 12 * 1024)
            self.assertTrue(path.read_bytes().startswith(b"\xff\xd8\xff"))
            self.assertTrue(path.read_bytes().endswith(b"\xff\xd9"), name)
        code = (ROOT / "android_app/verification_ui.py").read_text("utf-8")
        self.assertIn("mascot = _ASSETS / 'verification_mascot.jpg'", code)
        self.assertIn("castle = _ASSETS / 'verification_castle.jpg'", code)

    def test_app_still_uses_original_fail_closed_login_gate(self):
        source = (ROOT / "android_app/app.py").read_text("utf-8")
        self.assertIn("if self._login_ready():", source)
        self.assertIn("verified_for_login(", source)
        self.assertIn("self._verification_panel.apply_state(", source)
        self.assertIn("not connected or service.get('status') == 'checking'", source)
        self.assertIn("self._login_host.add_widget(self._verification_view)", source)


HAS_KIVY = importlib.util.find_spec("kivy") is not None


@unittest.skipUnless(HAS_KIVY and (os.environ.get("DISPLAY") or os.name == "nt"),
                     "Requires Kivy with Xvfb/desktop display")
class RealKivyTests(unittest.TestCase):
    def test_seven_actual_rows_and_dynamic_status(self):
        from android_app.verification_ui import VerificationDashboard
        called = []
        view = VerificationDashboard(lambda:called.append("retry"),
                                     lambda:called.append("service"))
        self.assertEqual(len(view.rows), 7)
        self.assertEqual(len(view.version_labels), 2)
        view.apply_state({"status": "checking"}, {},
                         connected=True, detail="正核對資源")
        self.assertEqual(view.rows["official"]._current, "checking")
        self.assertEqual(view.version_labels["DataPackage"].text, "— 尚未取得")
        view.apply_state({"status": "blocked",
                          **safe_display_receipt(observed_result(
                              failure="manifest_download_failed"))}, {},
                         connected=True, detail="Manifest 校驗失敗")
        self.assertEqual(view.rows["manifest"]._current, "blocked")
        self.assertIn("1286", view.version_labels["DataPackage"].text)
        self.assertIn("未通過", view.status.text)
        self.assertIn("尚未通過", view.hero.badge.text)
        view.retry.dispatch("on_release")
        view.service_button.dispatch("on_release")
        self.assertEqual(called, ["retry", "service"])

    def test_genuine_completion_and_scroll_view(self):
        from android_app.verification_ui import VerificationDashboard
        view = VerificationDashboard(lambda:None,lambda:None)
        service = {"status":"ready","ready":True,"catalog_token":TOKEN}
        local = {"status":"ready","ready":True,"catalog_token":TOKEN}
        view.apply_state(service,local,connected=True,login_ready=True,
                         detail="已確認")
        self.assertTrue(all(v._current == "passed"
                            for v in view.rows.values()))
        self.assertIn("驗證已完成", view.hero.badge.text)
        view.apply_state(service,local,connected=False,login_ready=True,
                         detail="服務失聯")
        self.assertIn("尚未通過", view.hero.badge.text)
        self.assertTrue(all(v._current != "passed"
                            for v in view.rows.values()))


if __name__ == "__main__":
    unittest.main()
