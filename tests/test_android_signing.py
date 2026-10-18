"""Persistent Android signing must never leak a keystore into source or logs."""
import base64
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from tools.android_signing import prepare, resign_apk, signing_info, _fingerprint, _configured_pin


FP_A = "aa" * 32
FP_B = "bb" * 32


class SigningTests(unittest.TestCase):
    def test_persistent_key_restored_private_and_reported(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            key = root / ".android/debug.keystore"
            github_env = root / "github-env"
            secret = base64.b64encode(b"X" * 256).decode("ascii")
            mock = Mock(side_effect=[
                Mock(stdout="SHA256: " + ":".join(["AA"] * 32) + "\n"),
                Mock(stdout="Signer #1 certificate SHA-256 digest: " + FP_A + "\n"),
                Mock(stdout="SHA256: " + ":".join(["AA"] * 32) + "\n"),
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
            self.assertIn("Certificate SHA256: " + ":".join(["AA"] * 32), report)
            self.assertNotIn(secret, report)
            self.assertNotIn("X" * 100, report)
            self.assertEqual(mock.call_count, 3)

    def test_mismatched_signing_certificate_fails_without_uploadable_report(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "app.apk").write_bytes(b"fixture")
            key = root / "debug.keystore"
            calls = [Mock(stdout="Signer #1 certificate SHA-256 digest: " + FP_B + "\n"),
                     Mock(stdout="SHA256: " + ":".join(["AA"] * 32) + "\n")]
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
                               "Signer #1 certificate SHA-256 digest: " + FP_B + "\n"))) as call:
                    result = signing_info(root, nonexistent_key, "test-apksigner")
            text = Path(result).read_text()
            self.assertIn("Mode: ephemeral", text)
            self.assertIn("Certificate SHA256: " + ":".join(["BB"] * 32), text)
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
                    "ANDROID_EXPECTED_SIGNER_SHA256": FP_A,
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
                    "ANDROID_EXPECTED_SIGNER_SHA256": FP_A,
                    "ANDROID_SIGNING_MODE": "ephemeral"}, clear=True):
                with self.assertRaisesRegex(RuntimeError, "refused"):
                    signing_info(folder, apk.parent / "debug.keystore",
                                 apksigner="apksigner")
            self.assertFalse((Path(folder) / "SIGNING_INFO.txt").exists())

    def test_pinned_signer_survives_repeated_builds(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            key = root / "debug.keystore"
            payload = base64.b64encode(b"Q" * 256).decode("ascii")
            for iteration in range(2):
                with self.subTest(build=iteration):
                    with patch.dict(os.environ, {
                            "ANDROID_REQUIRE_PERSISTENT_SIGNING": "1",
                            "ANDROID_EXPECTED_SIGNER_SHA256": ":".join(["AA"] * 32),
                            "ANDROID_SIGNING_MODE": "persistent"}, clear=True):
                        outputs = [
                            Mock(stdout="SHA256: " + ":".join(["AA"] * 32) + "\\n"),
                            Mock(stdout="Signer #1 certificate SHA-256 digest: " + FP_A + "\\n"),
                            Mock(stdout="SHA256: " + ":".join(["AA"] * 32) + "\\n"),
                        ]
                        with patch("tools.android_signing.subprocess.run",
                                   side_effect=outputs) as subprocess_mock:
                            self.assertTrue(prepare(payload, key))
                            (root / "app.apk").write_bytes(b"fixture")
                            report = Path(signing_info(root, key, "test-apksigner")).read_text()
                        self.assertEqual(subprocess_mock.call_count, 3)
                        self.assertIn("Pinned public signer SHA256: VERIFIED", report)

    def test_key_rotation_rejected_before_replacing_known_key(self):
        with tempfile.TemporaryDirectory() as folder:
            key = Path(folder) / "debug.keystore"
            key.write_bytes(b"previous-valid-key")
            encoded = base64.b64encode(b"Q" * 256).decode("ascii")
            with patch.dict(os.environ, {
                    "ANDROID_EXPECTED_SIGNER_SHA256": FP_A,
                    "ANDROID_REQUIRE_PERSISTENT_SIGNING": "1"}, clear=True):
                with patch("tools.android_signing.subprocess.run",
                           return_value=Mock(stdout="SHA256: " + FP_B + "\\n")):
                    with self.assertRaisesRegex(ValueError, "does not match pinned"):
                        prepare(encoded, key)
            self.assertEqual(key.read_bytes(), b"previous-valid-key")

    def test_apk_mismatch_with_pin_cannot_publish_report(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "app.apk").write_bytes(b"fixture")
            with patch.dict(os.environ, {
                    "ANDROID_SIGNING_MODE": "persistent",
                    "ANDROID_EXPECTED_SIGNER_SHA256": FP_A,
                    "ANDROID_REQUIRE_PERSISTENT_SIGNING": "1"}, clear=True):
                with patch("tools.android_signing.subprocess.run",
                           return_value=Mock(stdout="Signer #1 certificate SHA-256 digest: " +
                                             FP_B + "\\n")):
                    with self.assertRaisesRegex(ValueError, "does not match pinned"):
                        signing_info(root, root / "debug.keystore", "test-apksigner")
            self.assertFalse((root / "SIGNING_INFO.txt").exists())

    def test_missing_pin_rejected_for_required_build(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.dict(os.environ, {
                    "ANDROID_REQUIRE_PERSISTENT_SIGNING": "1",
                    "ANDROID_EXPECTED_SIGNER_SHA256": ""}, clear=True):
                with self.assertRaisesRegex(RuntimeError, "ANDROID_EXPECTED_SIGNER_SHA256"):
                    prepare(base64.b64encode(b"Q" * 256).decode("ascii"),
                            Path(folder) / "debug.keystore")
            self.assertFalse((Path(folder) / "debug.keystore").exists())

    def test_partial_and_multiple_signer_fingerprints_rejected(self):
        with self.assertRaisesRegex(ValueError, "complete"):
            _fingerprint("aabbcc")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "app.apk").write_bytes(b"fixture")
            result = "Signer #1 certificate SHA-256 digest: " + FP_A + "\\n"
            with patch.dict(os.environ, {"ANDROID_SIGNING_MODE": "ephemeral"}, clear=True):
                with patch("tools.android_signing.subprocess.run",
                           return_value=Mock(stdout=result + result)):
                    with self.assertRaisesRegex(ValueError, "exactly one"):
                        signing_info(root, apksigner="test-apksigner")

    def test_resign_apk_replaces_default_debug_signature_atomically(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            apk = root / "app.apk"
            apk.write_bytes(b"original-debug-signed-apk")
            key = root / "debug.keystore"
            key.write_bytes(b"private-fixture")
            calls = []

            def simulated_tool(command, **kwargs):
                calls.append(command)
                if command[0] == "keytool":
                    return Mock(stdout="SHA256: " + ":".join(["AA"] * 32) + "\n")
                if command[1] == "sign":
                    Path(command[command.index("--out") + 1]).write_bytes(
                        b"apk-signed-with-fixed-key")
                    return Mock(stdout="")
                if command[1] == "verify":
                    return Mock(stdout="Signer #1 certificate SHA-256 digest: " +
                                FP_A + "\n")
                raise AssertionError("unexpected command")

            with patch.dict(os.environ, {
                    "ANDROID_SIGNING_MODE": "persistent",
                    "ANDROID_EXPECTED_SIGNER_SHA256": FP_A,
                    "ANDROID_REQUIRE_PERSISTENT_SIGNING": "1"}, clear=True):
                with patch("tools.android_signing.subprocess.run",
                           side_effect=simulated_tool):
                    resign_apk(apk, key, "test-apksigner")
            self.assertEqual(apk.read_bytes(), b"apk-signed-with-fixed-key")
            self.assertEqual([cmd[1] for cmd in calls[1:]], ["sign", "verify"])
            self.assertFalse(list(root.glob(".lala-signed-*.apk")))

    def test_resign_mismatched_output_is_rejected_without_overwriting_apk(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            apk = root / "app.apk"
            apk.write_bytes(b"original")
            key = root / "debug.keystore"
            key.write_bytes(b"key")

            def simulated_tool(command, **kwargs):
                if command[0] == "keytool":
                    return Mock(stdout="SHA256: " + ":".join(["AA"] * 32) + "\n")
                if command[1] == "sign":
                    Path(command[command.index("--out") + 1]).write_bytes(b"bad")
                    return Mock(stdout="")
                return Mock(stdout="Signer #1 certificate SHA-256 digest: " +
                            FP_B + "\n")

            with patch.dict(os.environ, {
                    "ANDROID_SIGNING_MODE": "persistent",
                    "ANDROID_EXPECTED_SIGNER_SHA256": FP_A}, clear=True):
                with patch("tools.android_signing.subprocess.run",
                           side_effect=simulated_tool):
                    with self.assertRaisesRegex(ValueError, "Re-signed APK certificate"):
                        resign_apk(apk, key, "test-apksigner")
            self.assertEqual(apk.read_bytes(), b"original")
            self.assertFalse(list(root.glob(".lala-signed-*.apk")))

    def test_resign_requires_persistent_signing_and_pin(self):
        with tempfile.TemporaryDirectory() as folder:
            apk = Path(folder) / "app.apk"
            apk.write_bytes(b"original")
            with patch.dict(os.environ, {"ANDROID_SIGNING_MODE": "ephemeral"}, clear=True):
                with self.assertRaisesRegex(RuntimeError, "persistent signing"):
                    resign_apk(apk)
            with patch.dict(os.environ, {"ANDROID_SIGNING_MODE": "persistent"}, clear=True):
                with self.assertRaisesRegex(RuntimeError, "ANDROID_EXPECTED_SIGNER_SHA256"):
                    resign_apk(apk)
            self.assertEqual(apk.read_bytes(), b"original")

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
