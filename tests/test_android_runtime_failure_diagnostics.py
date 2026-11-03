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
from wlre.services.official_manifest_sync import ManifestSyncError
from wlre.services.official_bundle_download import BundleDownloadError
from wlre.services.world.catalog_identity import CatalogIdentityError
from wlre.services.world.unity_textasset import UnityTextAssetError


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

    def test_current_manifest_and_bundle_stages_have_fixed_diagnostics(self):
        cases = (
            (ManifestSyncError("Official Manifest download failed"),
             "manifest_download_failed", "Manifest 下載"),
            (ManifestSyncError("YooAsset full index parser (#53) is required"),
             "manifest_parser_missing", "Manifest 解碼"),
            (ManifestSyncError("YooAsset Manifest full index parse failed"),
             "manifest_parse_failed", "Manifest 結構"),
            (ManifestSyncError("Manifest identity or format differs from official .version"),
             "manifest_validation_failed", "Manifest 格式"),
            (CatalogIdentityError("Verified private Manifest is unreadable"),
             "manifest_identity_mismatch", "Manifest 與 Runtime"),
            (BundleDownloadError("Official Bundle download failed"),
             "bundle_download_failed", "Bundle 下載"),
            (BundleDownloadError("Official Bundle size/hash/CRC verification failed"),
             "bundle_integrity_failed", "Bundle 校驗"),
            (IncrementalSyncError("Required Bundle is invalid or exceeds safe size"),
             "bundle_integrity_failed", "Bundle 校驗"),
            (IncrementalSyncError("Missing Bundle dependency"),
             "bundle_plan_failed", "Bundle 依賴"),
            (UnityTextAssetError("Unity SerializedFile TextAsset decoding failed"),
             "runtime_parse_failed", "資料結構"),
            (DynamicRuntimeUnavailable("A newer official runtime check superseded this load"),
             "runtime_check_superseded", "更新的官方 Runtime"),
            (DynamicRuntimeUnavailable("Verified current-version catalog unavailable"),
             "runtime_catalog_unavailable", "完整 Runtime"),
            (OSError("/private/path secret=should-not-leak"),
             "resource_io_failed", "讀寫失敗"),
        )
        for exc, code, label in cases:
            with self.subTest(code=code):
                diagnostic = classify_runtime_failure(exc)
                self.assertEqual(diagnostic, {"code": code, "table": None})
                public = resource_message(self.blocked_report(diagnostic))
                self.assertIn(label, public)
                self.assertIn("禁止登入", public)
                self.assertNotIn(str(exc), public)

    def test_unknown_manifest_text_is_not_echoed_to_screen(self):
        secret = "PRIVATE-DEVICE-PATH secret=PRIVATE-PASSWORD"
        failure = classify_runtime_failure(ManifestSyncError(secret))
        self.assertEqual(failure, {"code": "manifest_validation_failed", "table": None})
        message = resource_message(self.blocked_report(failure))
        self.assertNotIn(secret, message)

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
