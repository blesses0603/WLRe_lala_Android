"""Policy checks for the pinned-signed Android ARM64 Cython APK workflow."""
from pathlib import Path
import unittest

from tools.android_release_version import source_version

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/android-apk.yml"


class NativeReleasePolicyTests(unittest.TestCase):
    def setUp(self):
        self.text = WORKFLOW.read_text(encoding="utf-8")

    def test_versioned_release_is_a_distinct_upgrade(self):
        self.assertEqual(source_version(
            ROOT / "buildozer.spec", ROOT / "android_app/version.py"), "v0.0.8")

    def test_full_apk_only_on_tag_or_main_manual_not_pull_request(self):
        self.assertIn("workflow_dispatch:", self.text)
        self.assertIn("tags:", self.text)
        self.assertIn("v*.*.*", self.text)
        self.assertNotIn("pull_request:", self.text)
        self.assertIn("python tools/android_release_version.py", self.text)
        self.assertIn("git merge-base --is-ancestor HEAD origin/main", self.text)

    def test_manual_dispatch_rejects_non_main_release_branches(self):
        # Workflow dispatch allows choosing any ref; do not let a feature
        # branch run the trusted pinned-signing release job.
        self.assertIn(
            "if: github.event_name != 'workflow_dispatch' || github.ref == 'refs/heads/main'",
            self.text,
        )

    def test_native_stage_precedes_access_to_signing_secret(self):
        stage = self.text.index("python tools/android_native_wire.py stage")
        private_key = self.text.index("secrets.ANDROID_DEBUG_KEYSTORE_BASE64")
        prepare = self.text.index("python tools/android_signing.py prepare")
        build = self.text.index("buildozer -v android debug")
        self.assertLess(stage, private_key)
        self.assertLess(private_key, prepare)
        self.assertLess(prepare, build)
        self.assertIn('NATIVE_STAGE: /tmp/wlre-android-native-release', self.text)
        self.assertIn('cd "$NATIVE_STAGE"', self.text)
        self.assertIn('"Cython==3.0.12"', self.text)

    def test_final_artifact_must_be_signed_native_verified_and_hashed(self):
        build = self.text.index("buildozer -v android debug")
        resign = self.text.index("python tools/android_signing.py resign")
        verified_native = self.text.index("python tools/android_native_wire.py report-apk")
        sign_check = self.text.index("python tools/android_signing.py report")
        hardening = self.text.index("python tools/android_hardening.py report")
        checksum = self.text.index('sha256sum "$output" > SHA256SUMS.txt')
        uploaded = self.text.index("uses: actions/upload-artifact")
        self.assertTrue(build < resign < verified_native < sign_check
                        < hardening < checksum < uploaded)
        self.assertIn('ANDROID_REQUIRE_PERSISTENT_SIGNING: \'1\'', self.text)
        self.assertIn("vars.ANDROID_EXPECTED_SIGNER_SHA256", self.text)
        self.assertIn("libpybundle", (ROOT / "tools/android_native_wire.py").read_text())
        self.assertIn("NATIVE_WIRE_INFO.txt", (ROOT / "tools/android_native_wire.py").read_text())

    def test_python_sources_are_not_replaced_in_default_checkout(self):
        config = (ROOT / "buildozer.spec").read_text(encoding="utf-8")
        self.assertNotIn("lalawire", config)
        self.assertNotIn("p4a.local_recipes", config)
        self.assertIn("android.archs = arm64-v8a", config)
        self.assertIn("p4a.commit = 8ef9d1dbbf769d2c14681dbc3c116c85e2e93bae", config)


if __name__ == "__main__":
    unittest.main()
