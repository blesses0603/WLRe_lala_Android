"""Policy and key regressions for safe reusable Android toolchain downloads."""
from pathlib import Path
import tempfile
import unittest

from tools.android_build_cache import cache_key

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/android-apk.yml"
TOOLS = {"buildozer": "1.5.0", "Cython": "3.0.12"}
PIN = "8ef9d1dbbf769d2c14681dbc3c116c85e2e93bae"


class AndroidBuildCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.spec = Path(self.temp.name) / "buildozer.spec"
        self.write_spec()

    def write_spec(self, *, app_version="7.1.3", p4a_commit=PIN,
                   requirements="python3,kivy==2.3.1,openssl", api=35):
        self.spec.write_text(
            "[app]\n"
            "version = " + app_version + "\n"
            "p4a.branch = develop\n"
            "p4a.commit = " + p4a_commit + "\n"
            "android.api = " + str(api) + "\n"
            "android.minapi = 31\n"
            "android.archs = arm64-v8a\n"
            "requirements = " + requirements + "\n",
            encoding="utf-8",
        )

    def key(self, versions=None):
        return cache_key(self.spec, tool_versions=TOOLS if versions is None else versions)

    def test_repeatable_and_app_patch_does_not_invalidate_platform_downloads(self):
        expected = self.key()
        self.assertRegex(expected, r"^[0-9a-f]{32}$")
        self.assertEqual(self.key(), expected)
        self.write_spec(app_version="7.1.4")
        self.assertEqual(self.key(), expected)

    def test_dependency_p4a_sdk_and_builder_changes_invalidate(self):
        before = self.key()
        self.write_spec(requirements="python3,kivy==2.3.1,openssl,liblzma")
        self.assertNotEqual(self.key(), before)
        self.write_spec(p4a_commit="f" * 40)
        self.assertNotEqual(self.key(), before)
        self.write_spec(api=36)
        self.assertNotEqual(self.key(), before)
        self.write_spec()
        self.assertNotEqual(
            self.key({"buildozer": "1.6.0", "Cython": "3.0.12"}), before)

    def test_rejects_unpinned_or_unsupported_build_inputs(self):
        self.write_spec(p4a_commit="develop")
        with self.assertRaises(ValueError):
            self.key()
        self.write_spec()
        with self.assertRaises(ValueError):
            self.key({"buildozer": "1.5.0"})

    def test_cache_paths_contain_only_reusable_build_dependencies(self):
        content = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("cache: pip", content)
        self.assertIn("python tools/android_build_cache.py", content)
        restore = content.index("uses: actions/cache/restore@v4")
        save = content.index("uses: actions/cache/save@v4")
        build = content.index("buildozer -v android debug")
        audit = content.index('sha256sum "$output" > SHA256SUMS.txt')
        upload = content.index("uses: actions/upload-artifact")
        self.assertLess(restore, build)
        self.assertTrue(build < audit < save < upload)
        self.assertIn("steps.android_dependency_cache.outputs.cache-hit != 'true'", content)
        # The SDK/NDK cache must use an exact immutable key. The new
        # ccache cache intentionally uses compiler-validated prefix restores.
        sdk_restore = content[restore:content.index("      - name:", restore)]
        self.assertNotIn("restore-keys:", sdk_restore)
        # Original SDK/NDK + new ccache + pinned third-party recipe
        # restore/save actions all fail open without bypassing APK gates.
        self.assertEqual(content.count("continue-on-error: true"), 6)
        for path in (
            "~/.buildozer/android/platform/android-sdk",
            "~/.buildozer/android/platform/android-ndk-r28c",
            "~/.gradle/caches/modules-2",
            "~/.gradle/wrapper/dists",
        ):
            self.assertEqual(content.count(path), 2)
        for segment in (
            content[restore:content.index("      - name:", restore)],
            content[save:content.index("      - name:", save)],
        ):
            for forbidden in (
                "NATIVE_STAGE", "private.tar", "android-output", "keystore",
                "secrets.", ".so", "wlre/", "android_app/", "bin/",
            ):
                self.assertNotIn(forbidden, segment)


if __name__ == "__main__":
    unittest.main()
