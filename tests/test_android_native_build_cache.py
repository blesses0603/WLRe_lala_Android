"""Regression tests for P1 compiler cache and P2 pinned third-party builds."""
from pathlib import Path
import tempfile
import unittest

from tools.android_build_cache import (
    P4A_THIRD_PARTY_FOLDERS,
    P4A_THIRD_PARTY_PACKAGE_FOLDERS,
    native_cache_key,
    safe_third_party_paths,
)

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/android-apk.yml"
SPEC = ROOT / "buildozer.spec"
TOOL_VERSIONS = {"buildozer": "1.5.0", "Cython": "3.0.12"}


class AndroidNativeBuildCacheTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        self.recipes = Path(self.work.name) / "p4a-recipes"
        target = self.recipes / "lz4"
        target.mkdir(parents=True)
        (target / "__init__.py").write_text("recipe = 1\n", encoding="utf-8")

    def key(self, image="20261103.1"):
        return native_cache_key(
            SPEC, recipes_root=self.recipes, image_version=image,
            tool_versions=TOOL_VERSIONS,
        )

    def test_native_key_reusable_for_identical_inputs(self):
        self.assertRegex(self.key(), r"^[0-9a-f]{32}$")
        self.assertEqual(self.key(), self.key())

    def test_runner_image_and_local_recipe_changes_invalidate(self):
        expected = self.key()
        self.assertNotEqual(self.key("20261104.1"), expected)
        (self.recipes / "lz4" / "__init__.py").write_text(
            "recipe = 2\n", encoding="utf-8")
        self.assertNotEqual(self.key(), expected)

    def test_missing_or_unknown_image_disables_compiled_reuse(self):
        self.assertIsNone(self.key(""))
        self.assertIsNone(self.key("../unexpected"))
        with self.assertRaises(ValueError):
            native_cache_key(
                SPEC, recipes_root=Path(self.work.name) / "missing",
                image_version="20261103.1", tool_versions=TOOL_VERSIONS,
            )

    def test_p2_cache_is_narrowly_limited_to_thirdparty_recipe_roots(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        names = set(P4A_THIRD_PARTY_FOLDERS)
        self.assertEqual(len(names), 10)
        self.assertIn("hostpython3", names)
        self.assertIn("python3-liblzma", names)
        self.assertIn("openssl", names)
        self.assertIn("sqlite3", names)
        paths = safe_third_party_paths()
        self.assertEqual(len(paths), 20)
        self.assertEqual(len(paths), len(set(paths)))
        self.assertTrue(any("/packages/python3" in p for p in paths))
        for path in paths:
            yaml_path = "${{ env.NATIVE_STAGE }}/" + path
            self.assertEqual(text.count(yaml_path), 2)
            self.assertNotIn("lala", path.lower())
        self.assertEqual(len(P4A_THIRD_PARTY_PACKAGE_FOLDERS), 10)

        # Scope P2 to the restore and save steps only. No dists, compiled
        # LaLa extensions, global installed modules, private app or keystore.
        before = text.index("      - name: Restore pinned third-party p4a recipe builds")
        stop = text.index("      - name: Pin public signer into Phase07 runtime Java guard")
        restore = text[before:stop]
        save_start = text.index("      - name: Save checked third-party p4a recipe builds")
        upload = text.index("      - name: Upload APK (only after successful build)")
        save = text[save_start:upload]
        for fragment in (restore, save):
            self.assertIn("native_enabled == 'true'", fragment)
            self.assertIn("continue-on-error: true", fragment)
            self.assertNotIn("restore-keys:", fragment)
            for forbidden in (
                "/dists", "/bootstrap_builds", "/python-installs",
                "/build/libs_collections", "/build/other_builds/lala",
                "android-output", "keystore", "secrets.",
            ):
                self.assertNotIn(forbidden, fragment)

    def test_ccache_is_installed_wired_and_saved_after_apk_gate(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("git zip unzip ccache", text)
        for required in (
            "CCACHE_COMPILERCHECK: content", "USE_CCACHE: '1'",
            "CCACHE_DIR:", "ccache --zero-stats",
            "ccache --show-stats", "ccache --version",
            "uses: actions/cache/restore@v4",
            "uses: actions/cache/save@v4",
            "lala-ndk-ccache-v1-",
        ):
            self.assertIn(required, text)
        self.assertIn("restore-keys:", text)
        signed_audit = text.index("python tools/android_release_gate.py")
        save_ccache = text.index("      - name: Save vetted NDK compiler ccache")
        save_p4a = text.index("      - name: Save checked third-party p4a recipe builds")
        upload = text.index("      - name: Upload APK")
        self.assertTrue(signed_audit < save_ccache < save_p4a < upload)
        self.assertIn("github.run_id", text)
        self.assertIn("github.run_attempt", text)

    def test_pr_build_still_does_not_access_signer_or_full_build(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("refs/heads/main", text)
        self.assertNotIn("pull_request:", text)
        self.assertIn("python tools/android_native_cores.py report-apk", text)
        self.assertIn("python tools/android_signing.py resign", text)
        self.assertIn("python tools/android_hardening.py report", text)


if __name__ == "__main__":
    unittest.main()
