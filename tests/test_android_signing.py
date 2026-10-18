"""Persistent Android signing must never leak a keystore into source or logs."""
import base64
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from tools.android_signing import prepare, signing_info


class SigningTests(unittest.TestCase):
    def test_persistent_key_restored_private_and_reported(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            key = root / ".android/debug.keystore"
            github_env = root / "github-env"
            secret = base64.b64encode(b"X" * 256).decode("ascii")
            mock = Mock(side_effect=[
                Mock(stdout="alias verified"),
                Mock(stdout="Signer #1 certificate SHA-256 digest: aabbccdd\n"),
                Mock(stdout="SHA256: AA:BB:CC:DD\n"),
            ])
            with patch.dict(os.environ, {"GITHUB_ENV": str(github_env),
                                         "ANDROID_SIGNING_MODE": "persistent"}):
                with patch("tools.android_signing.subprocess.run", mock):
                    self.assertTrue(prepare(secret, key))
                    self.assertEqual(key.read_bytes(), b"X" * 256)
                    self.assertEqual(key.stat().st_mode & 0o777, 0o600)
                    (root / "app.apk").write_bytes(b"fixture package")
                    path = Path(signing_info(root, key, "test-apksigner"))
            self.assertIn("ANDROID_SIGNING_MODE=persistent", github_env.read_text())
            report = path.read_text()
            self.assertIn("Mode: persistent", report)
            self.assertIn("Certificate SHA256: AA:BB:CC:DD", report)
            self.assertNotIn(secret, report)
            self.assertNotIn("X" * 100, report)
            self.assertEqual(mock.call_count, 3)

    def test_mismatched_signing_certificate_fails_without_uploadable_report(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "app.apk").write_bytes(b"fixture")
            key = root / "debug.keystore"
            calls = [Mock(stdout="Signer #1 certificate SHA-256 digest: 1122\n"),
                     Mock(stdout="SHA256: AA:BB\n")]
            with patch.dict(os.environ, {"ANDROID_SIGNING_MODE": "persistent"}):
                with patch("tools.android_signing.subprocess.run", side_effect=calls):
                    with self.assertRaisesRegex(ValueError, "does not match"):
                        signing_info(root, key, "test-apksigner")
            self.assertFalse((root / "SIGNING_INFO.txt").exists())

    def test_ephemeral_build_reads_actual_apk_certificate_without_keystore(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "app.apk").write_bytes(b"fixture")
            nonexistent_key = root / "missing.keystore"
            with patch.dict(os.environ, {"ANDROID_SIGNING_MODE": "ephemeral"}):
                with patch("tools.android_signing.subprocess.run",
                           return_value=Mock(stdout=(
                               "Signer #1 certificate SHA-256 digest: 11223344\n"))) as call:
                    result = signing_info(root, nonexistent_key, "test-apksigner")
            text = Path(result).read_text()
            self.assertIn("Mode: ephemeral", text)
            self.assertIn("Certificate SHA256: 11:22:33:44", text)
            self.assertIn("signature may change", text)
            call.assert_called_once()
            self.assertFalse(nonexistent_key.exists())

    def test_missing_secret_warns_and_does_not_write_fake_key(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            key = root / "debug.keystore"
            env_file = root / "github-env"
            with patch.dict(os.environ, {"GITHUB_ENV": str(env_file)}):
                self.assertFalse(prepare("", key))
            self.assertFalse(key.exists())
            self.assertIn("ANDROID_SIGNING_MODE=ephemeral", env_file.read_text())

    def test_tagged_build_rejects_missing_signing_secret(self):
        with tempfile.TemporaryDirectory() as folder:
            key = Path(folder) / "debug.keystore"
            with patch.dict(os.environ, {
                    "ANDROID_REQUIRE_PERSISTENT_SIGNING": "1",
                    "ANDROID_DEBUG_KEYSTORE_BASE64": "",
                    "GITHUB_ENV": str(Path(folder) / "env")}, clear=True):
                with self.assertRaisesRegex(RuntimeError, "mandatory"):
                    prepare("", key)
            self.assertFalse(key.exists())

    def test_tagged_build_cannot_publish_ephemeral_signing_report(self):
        with tempfile.TemporaryDirectory() as folder:
            apk = Path(folder) / "test.apk"
            apk.write_bytes(b"fixture")
            with patch.dict(os.environ, {
                    "ANDROID_REQUIRE_PERSISTENT_SIGNING": "1",
                    "ANDROID_SIGNING_MODE": "ephemeral"}, clear=True):
                with self.assertRaisesRegex(RuntimeError, "refused"):
                    signing_info(folder, apk.parent / "debug.keystore",
                                 apksigner="apksigner")
            self.assertFalse((Path(folder) / "SIGNING_INFO.txt").exists())

    def test_bad_secret_fails_without_ephemeral_fallback(self):
        with tempfile.TemporaryDirectory() as folder:
            key = Path(folder) / "debug.keystore"
            with self.assertRaisesRegex(ValueError, "Invalid base64"):
                prepare("NOT_VALID***", key)
            self.assertFalse(key.exists())

    def test_keytool_failure_does_not_replace_existing_keystore(self):
        with tempfile.TemporaryDirectory() as folder:
            key = Path(folder) / "debug.keystore"
            key.write_bytes(b"original")
            secret = base64.b64encode(b"Y" * 256).decode("ascii")
            with patch("tools.android_signing.subprocess.run",
                       side_effect=__import__("subprocess").CalledProcessError(1, "keytool")):
                with self.assertRaises(__import__("subprocess").CalledProcessError):
                    prepare(secret, key)
            self.assertEqual(key.read_bytes(), b"original")
