"""Keep cheap PR CI and explicit signed ARM64 builds separate.

This policy test runs without Buildozer or GitHub Secrets and fails if a future
workflow edit silently restores automatic APK packaging on every code change.
"""
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
FAST = ROOT / ".github" / "workflows" / "android-smoke.yml"
PHONE = ROOT / ".github" / "workflows" / "android-apk.yml"


class AndroidCIPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fast = FAST.read_text(encoding="utf-8")
        cls.phone = PHONE.read_text(encoding="utf-8")

    def test_pr_and_main_only_run_fast_checks(self):
        self.assertRegex(self.fast, r"(?m)^  push:\s*\n    branches: \[main\]")
        self.assertRegex(self.fast, r"(?m)^  pull_request:\s*\n    branches: \[main\]")
        self.assertIn("xvfb-run -a python -m unittest discover -s tests -q", self.fast)
        self.assertIn("python tools/android_hardening.py preflight", self.fast)
        self.assertIn("python tools/android_presplash.py check-spec", self.fast)
        self.assertIn("source_version(", self.fast)
        self.assertIn("python -m compileall", self.fast)
        self.assertIn("android.archs = arm64-v8a", self.fast)

    def test_fast_checks_cannot_build_or_publish_any_apk(self):
        for disallowed in (
            "buildozer -v android debug",
            "upload-artifact@",
            "android_signing.py prepare",
            "android_signing.py resign",
            "ANDROID_DEBUG_KEYSTORE_BASE64",
            "secrets.",
            "phone-output/",
        ):
            with self.subTest(disallowed=disallowed):
                self.assertNotIn(disallowed, self.fast)
        self.assertNotRegex(self.fast, r"(?m)^    tags:")
        self.assertRegex(self.fast, r"(?m)^    timeout-minutes: 20$")

    def test_full_build_only_on_manual_dispatch_or_version_tag(self):
        self.assertIn("workflow_dispatch:", self.phone)
        self.assertRegex(self.phone, r"(?m)^  push:\s*\n    tags:\s*\n      - 'v\*\.\*\.\*'")
        self.assertNotRegex(self.phone, r"(?m)^  pull_request:")
        self.assertNotRegex(self.phone, r"(?m)^    branches:")
        self.assertIn("python tools/android_release_version.py", self.phone)
        self.assertIn("buildozer -v android debug", self.phone)

    def test_manual_and_tagged_apk_always_keep_persistent_signature_and_audit(self):
        for required in (
            "ANDROID_DEBUG_KEYSTORE_BASE64",
            "ANDROID_EXPECTED_SIGNER_SHA256",
            "ANDROID_REQUIRE_PERSISTENT_SIGNING: '1'",
            "python tools/android_signing.py prepare",
            "python tools/android_signing.py resign",
            "python tools/android_signing.py report",
            "python tools/android_hardening.py report",
            "python tools/android_presplash.py check-apk",
            "sha256sum",
            "actions/upload-artifact@",
        ):
            with self.subTest(required=required):
                self.assertIn(required, self.phone)


if __name__ == "__main__":
    unittest.main()
