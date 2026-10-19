"""Phase10 final-Artifact trust gates and read-only physical device validation."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from tools.android_phase10_acceptance import (
    EVIDENCE, EVIDENCE_HASHES, APK_HASHES, PACKAGE, REQUIRED_REPORTS,
    _sha, device_preflight, verify_artifact,
)

ROOT = Path(__file__).resolve().parents[1]
PIN = "ab" * 32
COMMIT = "af355ccd5e00744d1ea142f98a8f0fa7e1c4e3fa"
VERSION = "0.0.8"
APK_NAME = "WLRe_LaLa-Android-v" + VERSION + "-debug.apk"


class ArtifactReceiptTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.out = self.root / "artifact"
        self.out.mkdir()
        self.apk = self.out / APK_NAME
        with zipfile.ZipFile(self.apk, "w") as blob:
            blob.writestr("classes.dex", b"synthetic-dex")
        self.evidence = {
            "schema_version": 1,
            "project": "WLRe_LaLa_Android",
            "apk": {
                "filename": APK_NAME,
                "sha256": _sha(self.apk),
                "size_bytes": self.apk.stat().st_size,
                "package": PACKAGE, "version_name": VERSION,
                "version_code": 8, "min_sdk": 31, "target_sdk": 35,
                "abi": "arm64-v8a",
            },
            "source": {
                "commit_sha": COMMIT, "git_ref": "refs/heads/main",
                "event": "workflow_dispatch",
            },
            "public_certificate_sha256": PIN,
            "reports": {},
        }
        for name, markers in REQUIRED_REPORTS.items():
            text = "Phase10 synthetic report\n" + "\n".join(markers) + "\n"
            if name == "SIGNING_INFO.txt":
                text += "Certificate SHA256: " + PIN + "\n"
            (self.out / name).write_text(text, encoding="utf-8")
            self.evidence["reports"][name] = {
                "sha256": _sha(self.out / name),
                "size_bytes": (self.out / name).stat().st_size,
            }
        (self.out / APK_HASHES).write_text(
            _sha(self.apk) + "  " + APK_NAME + "\n", encoding="ascii")
        self.evidence["apk_sha256sums_sha256"] = _sha(self.out / APK_HASHES)
        (self.out / EVIDENCE).write_text(
            json.dumps(self.evidence, sort_keys=True) + "\n", encoding="utf-8")
        filenames = sorted(set(REQUIRED_REPORTS) | {APK_HASHES, EVIDENCE})
        (self.out / EVIDENCE_HASHES).write_text(
            "".join(_sha(self.out / n) + "  " + n + "\n" for n in filenames),
            encoding="ascii")

    def check(self, **kwargs):
        with patch("tools.android_phase10_acceptance._run",
                   return_value="Signer #1 certificate SHA-256 digest: " + PIN):
            return verify_artifact(
                self.out, apksigner="/fake/android-sdk/apksigner", **kwargs)

    def test_full_report_chain_signed_identity_and_expected_main_commit(self):
        value = self.check(expected_commit=COMMIT)
        self.assertEqual(value["signed_apk"], "verified")
        self.assertEqual(value["reports"], 7)
        self.assertEqual(value["physical_device_acceptance"], "not_performed")
        self.assertEqual(value["release_commit"], COMMIT)

    def test_wrong_commit_and_old_unsigned_build_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "expected main"):
            self.check(expected_commit="01" * 20)
        self.evidence["source"]["git_ref"] = "refs/heads/feature"
        self._rewrite_evidence()
        with self.assertRaisesRegex(ValueError, "main"):
            self.check()

    def _rewrite_evidence(self):
        (self.out / EVIDENCE).write_text(
            json.dumps(self.evidence, sort_keys=True) + "\n", encoding="utf-8")
        entries = sorted(set(REQUIRED_REPORTS) | {APK_HASHES, EVIDENCE})
        (self.out / EVIDENCE_HASHES).write_text(
            "".join(_sha(self.out / n) + "  " + n + "\n" for n in entries),
            encoding="ascii")

    def test_tampered_apk_and_report_rejected(self):
        with self.apk.open("ab") as stream:
            stream.write(b"new-binary")
        with self.assertRaisesRegex(ValueError, "bytes differ|size changed"):
            self.check()

    def test_tampered_report_and_manifest_rejected(self):
        (self.out / "NATIVE_VAULT_INFO.txt").write_text("tampered report")
        with self.assertRaisesRegex(ValueError, "Report checksum"):
            self.check()

    def test_deleted_report_and_added_private_keystore_rejected(self):
        missing = self.out / "PROTECTION_INFO.txt"
        missing.unlink()
        with self.assertRaisesRegex(ValueError, "missing mandatory"):
            self.check()
        missing.write_text("restored")
        unexpected = self.out / "secret.keystore"
        unexpected.write_bytes(b"NEVER PUBLISH")
        with self.assertRaisesRegex(ValueError, "extra files"):
            self.check()

    def test_wrong_actual_apksigner_certificate_rejected(self):
        with patch("tools.android_phase10_acceptance._run",
                   return_value="Signer #1 certificate SHA-256 digest: " + "cd" * 32):
            with self.assertRaisesRegex(ValueError, "Actual signed APK certificate"):
                verify_artifact(self.out, apksigner="/sdk/apksigner")
        with patch("tools.android_phase10_acceptance.shutil.which", return_value=None):
            with self.assertRaisesRegex(ValueError, "apksigner required"):
                verify_artifact(self.out)

    def test_report_checksum_file_and_json_duplicate_keys_rejected(self):
        path = self.out / EVIDENCE_HASHES
        path.write_text(path.read_text() + ("0" * 64) + "  OTHER.txt\n")
        with self.assertRaisesRegex(ValueError, "Incomplete Phase10"):
            self.check()
        self._rewrite_evidence()
        p = self.out / EVIDENCE
        p.write_text('{"schema_version":1,"schema_version":1}')
        with self.assertRaisesRegex(ValueError, "Duplicate evidence JSON key"):
            self.check()

    def test_symlink_to_external_report_is_rejected(self):
        report = self.out / "SIGNING_INFO.txt"
        other = self.root / "outside.txt"
        other.write_bytes(report.read_bytes())
        report.unlink()
        report.symlink_to(other)
        with self.assertRaisesRegex(ValueError, "extra files"):
            self.check()

    def test_unsigned_tag_mismatch_and_bad_version_code(self):
        self.evidence["source"]["event"] = "push"
        self.evidence["source"]["git_ref"] = "refs/tags/v0.0.9"
        self._rewrite_evidence()
        with self.assertRaisesRegex(ValueError, "ref differs"):
            self.check()
        self.evidence["source"]["git_ref"] = "refs/tags/v0.0.8"
        self.evidence["apk"]["version_code"] = 0
        self._rewrite_evidence()
        with self.assertRaisesRegex(ValueError, "positive"):
            self.check()

    def test_phase10_never_auto_installs_or_uploads_device_logs(self):
        source = (ROOT / "tools/android_phase10_acceptance.py").read_text()
        self.assertNotIn('"install", "-r"', source)
        self.assertNotIn("uninstall", source.split("def device_preflight")[1])
        self.assertNotIn('["logcat"', source.split("def device_preflight")[1])
        assert "device-preflight" in source


class PhysicalDeviceReadOnlyTests(unittest.TestCase):
    def test_physical_android_12_arm64_preflight(self):
        with patch("tools.android_phase10_acceptance._run",
                   side_effect=["35", "arm64-v8a,armeabi-v7a", "0"]) as call:
            data = device_preflight("TEST-SERIAL")
        self.assertEqual(data["android_sdk"], 35)
        self.assertEqual(data["physical_device"], "platform_signals_passed")
        self.assertEqual(data["login_and_keystore_test"], "not_performed")
        self.assertEqual(call.call_count, 3)
        self.assertEqual(call.call_args_list[0].args[0][0:3],
                         ["adb", "-s", "TEST-SERIAL"])

    def test_reject_emulator_older_sdk_and_32_bit(self):
        candidates = [
            (["30", "arm64-v8a", "0"], "Android 12"),
            (["35", "armeabi-v7a", "0"], "ARM64"),
            (["35", "arm64-v8a", "1"], "emulator"),
        ]
        for data, message in candidates:
            with self.subTest(data=data):
                with patch("tools.android_phase10_acceptance._run", side_effect=data):
                    with self.assertRaisesRegex(ValueError, message):
                        device_preflight("VALID_SERIAL")

    def test_empty_or_injected_serial_rejected_without_subprocess(self):
        for serial in ("", "one serial", "a;cat /etc/passwd", "A" * 101):
            with self.subTest(serial=serial):
                with patch("tools.android_phase10_acceptance._run") as cmd:
                    with self.assertRaisesRegex(ValueError, "serial"):
                        device_preflight(serial)
                    cmd.assert_not_called()


if __name__ == "__main__":
    unittest.main()
