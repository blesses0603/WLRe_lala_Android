"""Regression checks for Git Tag-driven Android APK numbering."""
import tempfile
import unittest
from pathlib import Path

from tools.android_release_version import resolve_version, source_version


class AndroidReleaseVersionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        folder = Path(self.temp.name)
        self.spec = folder / "buildozer.spec"
        self.version = folder / "version.py"
        self.set_versions("0.0.8", "0.0.8")

    def set_versions(self, spec, source):
        self.spec.write_text(f"[app]\nversion = {spec}\n", encoding="utf-8")
        self.version.write_text(f'ANDROID_VERSION = "{source}"\n', encoding="utf-8")

    def check(self, ref, event="push"):
        return resolve_version(self.spec, self.version, ref, event)

    def test_emulator_source_versions_match_without_git_tag(self):
        self.assertEqual(source_version(self.spec, self.version), "v0.0.8")

    def test_emulator_source_mismatch_fails(self):
        self.set_versions("0.0.8", "0.0.7")
        with self.assertRaisesRegex(ValueError, "Version mismatch"):
            source_version(self.spec, self.version)

    def test_emulator_source_invalid_version_fails(self):
        self.set_versions("0.0.8-beta", "0.0.8-beta")
        with self.assertRaisesRegex(ValueError, "Expected numeric"):
            source_version(self.spec, self.version)

    def test_matching_git_tag(self):
        self.assertEqual(self.check("refs/tags/v0.0.8"), "v0.0.8")

    def test_manual_build_from_main(self):
        self.assertEqual(self.check("refs/heads/main", "workflow_dispatch"), "v0.0.8")

    def test_wrong_tag_rejected(self):
        with self.assertRaisesRegex(ValueError, "does not match"):
            self.check("refs/tags/v0.0.7")

    def test_manual_build_from_other_branch_rejected(self):
        with self.assertRaisesRegex(ValueError, "must use main"):
            self.check("refs/heads/feature", "workflow_dispatch")

    def test_mismatching_version_files_rejected(self):
        self.set_versions("0.0.8", "0.0.7")
        with self.assertRaisesRegex(ValueError, "Version mismatch"):
            self.check("refs/tags/v0.0.8")

    def test_invalid_version_rejected(self):
        self.set_versions("0.0.8-beta", "0.0.8-beta")
        with self.assertRaisesRegex(ValueError, "Expected numeric"):
            self.check("refs/tags/v0.0.8-beta")

    def test_unsupported_event_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unsupported"):
            self.check("refs/heads/main", "pull_request")


if __name__ == "__main__":
    unittest.main()
