"""Test the debug APK's real security boundaries, without distributing keys."""
from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from tools.android_hardening import (
    check_apk, check_configuration, check_files, report, ROOT,
)


def fixture(root, *, backup="False", excludes=None):
    for directory in ("android_app", "wlre", "tools"):
        (root / directory).mkdir()
    exclude = excludes or ".git,.github,tests,tools,.buildozer,bin"
    (root / "buildozer.spec").write_text(
        "[app]\nandroid.allow_backup = " + backup +
        "\nsource.dir = .\nsource.exclude_dirs = " + exclude + "\n",
        encoding="utf-8",
    )


class AndroidHardeningTests(unittest.TestCase):
    def test_real_spec_excludes_development_sources_and_backups(self):
        self.assertTrue(check_configuration(ROOT))
        self.assertTrue(check_files(ROOT))

    def test_unprotected_backup_or_test_directory_in_build_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fixture(root, backup="True")
            with self.assertRaisesRegex(ValueError, "backups"):
                check_configuration(root)
            fixture(root, excludes=".git,.github,tools,.buildozer,bin")
            with self.assertRaisesRegex(ValueError, "excludes"):
                check_configuration(root)

    def test_private_key_file_cannot_enter_build_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fixture(root)
            (root / "android_app" / "credentials.keystore").write_bytes(b"not a real key")
            with self.assertRaisesRegex(ValueError, "credential file"):
                check_files(root)

    def test_private_key_material_is_detected_without_printing_it(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fixture(root)
            secret = ("-----BEGIN " + "PRIVATE KEY-----").encode()
            (root / "wlre" / "bad.py").write_bytes(b"token = " + secret)
            with self.assertRaisesRegex(ValueError, "Private credential material") as found:
                check_files(root)
            self.assertNotIn(secret.decode(), str(found.exception))

    def test_apk_rejects_bundled_signing_keystore(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / "demo.apk"
            with zipfile.ZipFile(archive, "w") as stream:
                stream.writestr("assets/debug.keystore", "DO_NOT_BUNDLE_PRIVATE_KEYS")
            with self.assertRaisesRegex(ValueError, "credential file"):
                check_apk(archive)
            self.assertFalse((Path(temp) / "PROTECTION_INFO.txt").exists())

    def test_protection_report_does_not_claim_reverse_engineering_prevention(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / "demo.apk"
            with zipfile.ZipFile(archive, "w") as stream:
                stream.writestr("classes.dex", b"dex\n")
            output = report(archive).read_text()
            self.assertIn("NOT enabled", output)
            self.assertIn("public GitHub", output)
            self.assertIn("APK private-key/credential filename audit: PASSED", output)


if __name__ == "__main__":
    unittest.main()
