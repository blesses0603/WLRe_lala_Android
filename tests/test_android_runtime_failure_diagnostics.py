"""The Android login gate reports safe Runtime stage codes without unlocking login."""
import sys
import unittest
from types import ModuleType
from unittest.mock import patch

from android_app.resource_sync import ResourceSync, resource_message
from wlre.services.game_version_gate import classify_runtime_failure
from wlre.services.world.bundle_runtime_1275 import BundleRuntimeUnavailable
from wlre.services.world.dynamic_bundle_runtime import DynamicRuntimeUnavailable
from wlre.services.official_incremental_sync import IncrementalSyncError


class AndroidRuntimeFailureDiagnostics(unittest.TestCase):
    def blocked_report(self, diagnostic):
        return {
            "status": "runtime_unavailable",
            "message": "官方版本已確認；目前版本的完整 Runtime 未通過驗證，禁止登入。",
            "block_reason": "runtime_unavailable",
            "runtime_failure": diagnostic,
            "login_allowed": False,
            "database_verified": False,
            "blocked": True,
        }

    def test_missing_bundle_reports_fixed_table_not_private_payload(self):
        exc = BundleRuntimeUnavailable("仍缺少官方 Bundle：Eve")
        diagnostic = classify_runtime_failure(exc)
        self.assertEqual(diagnostic, {"code": "required_bundle_missing", "table": "Eve"})
        message = resource_message(self.blocked_report(diagnostic))
        self.assertIn("必要 Bundle", message)
        self.assertIn("（Eve）", message)
        self.assertIn("禁止登入", message)

    def test_invalid_bundle_and_parser_stage_are_separate(self):
        checksum = classify_runtime_failure(
            BundleRuntimeUnavailable("Bundle 來源校驗失敗：ItemData_C"))
        schema = classify_runtime_failure(
            BundleRuntimeUnavailable("官方 Bundle 的資料格式無法建立完整 1275 Runtime：Eve"))
        self.assertEqual(checksum, {"code": "required_bundle_invalid", "table": "ItemData_C"})
        self.assertEqual(schema, {"code": "runtime_parse_failed", "table": "Eve"})
        self.assertNotEqual(checksum["code"], schema["code"])

    def test_quota_and_version_change_are_not_misreported_as_tls(self):
        quota = classify_runtime_failure(
            IncrementalSyncError("Planned downloads exceed the explicit byte/file quota"))
        changed = classify_runtime_failure(
            DynamicRuntimeUnavailable("Official versions changed during runtime load"))
        self.assertEqual(quota["code"], "download_limit")
        self.assertEqual(changed["code"], "official_version_changed")

    def test_untrusted_exception_text_and_unknown_table_never_escape(self):
        secret = "PRIVATE-DEVICE-PATH secret=PRIVATE-PASSWORD"
        failure = classify_runtime_failure(ValueError(secret))
        text = resource_message(self.blocked_report(failure))
        self.assertEqual(failure["code"], "runtime_check_failed")
        self.assertNotIn(secret, text)
        forged = classify_runtime_failure(
            BundleRuntimeUnavailable("仍缺少官方 Bundle：" + secret))
        self.assertIsNone(forged["table"])
        self.assertNotIn(secret, resource_message(self.blocked_report(forged)))
        unknown = self.blocked_report({"code": secret, "table": secret})
        self.assertNotIn(secret, resource_message(unknown))

    def test_preparation_quota_diagnostic_preserves_fail_closed_state(self):
        def prepare(progress):
            progress("runtime_bundle_unavailable", {"code": "download_limit"})
        fake = ModuleType("wlre.services.world.dynamic_bundle_runtime")
        fake.current_catalog_token = lambda: ()
        sync = ResourceSync(download=True, preparer=prepare,
                            checker=lambda: self.blocked_report(
                                {"code": "required_bundle_missing", "table": "Eve"}))
        with patch.dict(sys.modules, {fake.__name__: fake}):
            sync._run()
        report = sync.snapshot()
        self.assertEqual(report["status"], "blocked")
        self.assertFalse(report["ready"])
        self.assertIn("32 MiB／24 檔", report["message"])
        self.assertIn("（Eve）", report["message"])
        self.assertNotIn("PRIVATE", report["message"])


if __name__ == "__main__":
    unittest.main()
