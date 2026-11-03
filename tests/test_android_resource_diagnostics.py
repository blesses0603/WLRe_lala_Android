"""Android resource checks retain public failure details without leaking payloads."""
import sys
from types import ModuleType
import unittest
from unittest.mock import patch
from android_app.resource_sync import ResourceSync, resource_message


class ResourceDiagnosticsTests(unittest.TestCase):
    def report(self, stage="ResourcePath_PC.dat", reason="TLS 憑證驗證失敗"):
        return {
            "message": "官方版本無法完整驗證；禁止登入，請重新查詢。",
            "blocked": True, "login_allowed": False, "database_verified": False,
            "remote": {
                "failed_stage": stage, "reason": reason,
                "packages": {"DataPackage": {"reason": reason}},
            },
        }

    def test_resource_map_tls_failure_is_identified(self):
        text = resource_message(self.report())
        self.assertIn("ResourcePath_PC.dat", text)
        self.assertIn("TLS 憑證驗證失敗", text)

    def test_package_failure_uses_its_own_reason(self):
        report = self.report("DataPackage.version", "連線逾時")
        report["remote"]["reason"] = "TLS 憑證驗證失敗"
        text = resource_message(report)
        self.assertIn("DataPackage.version", text)
        self.assertIn("連線逾時", text)
        self.assertNotIn("TLS", text)

    def test_http_status_is_bounded(self):
        text = resource_message(self.report(reason="HTTP 403（官方 CDN 拒絕或找不到檔案）"))
        self.assertIn("HTTP 403", text)

    def test_private_or_remote_error_text_is_not_echoed(self):
        report = self.report(reason="PRIVATE-DEVICE-PATH token=SECRET")
        text = resource_message(report)
        self.assertNotIn("PRIVATE", text)
        self.assertNotIn("SECRET", text)
        self.assertIn("版本資料不完整", text)
        report["remote"]["failed_stage"] = "PRIVATE-DEVICE-PATH"
        self.assertEqual(resource_message(report), report["message"])

    def test_unknown_shapes_and_success_keep_original_message(self):
        for remote in (None, [], {}, {"failed_stage": []}):
            report = self.report()
            report["remote"] = remote
            self.assertEqual(resource_message(report), report["message"])
        report = self.report()
        report["login_allowed"] = True
        self.assertEqual(resource_message(report), report["message"])

    def test_blocked_worker_keeps_login_blocked_and_exposes_diagnosis(self):
        runtime = ModuleType("wlre.services.world.dynamic_bundle_runtime")
        runtime.current_catalog_token = lambda: ()
        sync = ResourceSync(download=False, checker=lambda: self.report())
        with patch.dict(sys.modules, {runtime.__name__: runtime}):
            sync._run()
        status = sync.snapshot()
        self.assertFalse(status["ready"])
        self.assertEqual(status["status"], "blocked")
        self.assertIn("TLS 憑證驗證失敗", status["message"])

    def test_malformed_reason_does_not_hide_blocked_state(self):
        report = self.report(reason={"untrusted": "SECRET"})
        self.assertIn("版本資料不完整", resource_message(report))


if __name__ == "__main__":
    unittest.main()
