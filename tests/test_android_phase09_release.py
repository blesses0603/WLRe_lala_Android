"""Phase09 signed ARM64 APK metadata, required evidence and publication policy."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile

from tools.android_release_gate import (
    PACKAGE, REQUIRED_REPORTS, APK_HASHES, EVIDENCE, EVIDENCE_HASHES,
    _apk_metadata, _digest, finalize_release, verify_release,
)

ROOT = Path(__file__).resolve().parents[1]
PIN = "a1" * 32
SHA = "c3" * 20
VERSION = "v0.0.8"
APK = f"WLRe_LaLa-Android-{VERSION}-debug.apk"
AAPT_GOOD = (
    "package: name='org.lala.client.wlrelala' versionCode='8' versionName='0.0.8'\n"
    "sdkVersion:'31'\n"
    "targetSdkVersion:'35'\n"
    "native-code: 'arm64-v8a'\n"
)


class Phase09GateTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.output = self.root / "out"
        self.output.mkdir()
        self.source = self.root / "checkout"
        self.source.mkdir()
        (self.source / "android_app").mkdir()
        shutil.copy2(ROOT / "buildozer.spec", self.source / "buildozer.spec")
        shutil.copy2(ROOT / "android_app/version.py",
                     self.source / "android_app/version.py")
        apk = self.output / APK
        with zipfile.ZipFile(apk, "w") as archive:
            archive.writestr("classes.dex", b"dex\n035\0sample")
            archive.writestr("lib/arm64-v8a/libpython3.14.so", b"synthetic binary")
        self.apk = apk
        for name, markers in REQUIRED_REPORTS.items():
            content = "WLRe_LaLa Android evidence\n" + "\n".join(markers) + "\n"
            if name == "SIGNING_INFO.txt":
                content += f"Certificate SHA256: {PIN}\n"
            (self.output / name).write_text(content, encoding="utf-8")
        (self.output / APK_HASHES).write_text(
            f"{_digest(apk)}  {apk.name}\n", encoding="ascii",
        )

    def verify(self, **extra):
        params = dict(
            expected_version=VERSION, source_root=self.source,
            source_sha=SHA, git_ref="refs/heads/main",
            event="workflow_dispatch", expected_signer=PIN,
        )
        params.update(extra)
        with patch("tools.android_release_gate.subprocess.run",
                   return_value=Mock(stdout=AAPT_GOOD)) as cmd:
            return verify_release(self.output, aapt="aapt", **params)

    def finalize(self, **extra):
        params = dict(
            expected_version=VERSION, source_root=self.source,
            source_sha=SHA, git_ref="refs/heads/main",
            event="workflow_dispatch", expected_signer=PIN,
        )
        params.update(extra)
        with patch("tools.android_release_gate.subprocess.run",
                   return_value=Mock(stdout=AAPT_GOOD)):
            return finalize_release(self.output, aapt="aapt", **params)

    def test_success_persistent_signed_release_generates_complete_manifest(self):
        data = self.verify()
        self.assertEqual(data["apk"]["package"], PACKAGE)
        self.assertEqual(data["apk"]["version_code"], 8)
        self.assertEqual(data["public_certificate_sha256"], PIN)
        self.assertEqual(len(data["reports"]), len(REQUIRED_REPORTS))
        self.assertNotIn("private", json.dumps(data).lower().replace(
            '"android_real_device_test": "not_claimed"', ""))
        manifest = self.finalize()
        disk = json.loads(manifest.read_text(encoding="utf-8"))
        self.assertEqual(disk, data)
        self.assertTrue((self.output / EVIDENCE_HASHES).is_file())
        lines = (self.output / EVIDENCE_HASHES).read_text().splitlines()
        self.assertEqual(len(lines), len(REQUIRED_REPORTS) + 2)
        self.assertIn(f"{_digest(manifest)}  {EVIDENCE}", lines)
        with self.assertRaisesRegex(ValueError, "already finalized"):
            self.finalize()

    def test_missing_or_forged_report_blocks_publication(self):
        for missing in REQUIRED_REPORTS:
            with self.subTest(missing=missing):
                path = self.output / missing
                data = path.read_bytes()
                path.unlink()
                with self.assertRaisesRegex(ValueError, "Incomplete"):
                    self.verify()
                path.write_bytes(data)
        path = self.output / "PHASE05_ALL_CORES_INFO.txt"
        original = path.read_text()
        path.write_text(original.replace(
            "Python implementations of these six cores exposed: 0",
            "Python implementations of these six cores exposed: 6"))
        with self.assertRaisesRegex(ValueError, "report has not passed"):
            self.verify()

    def test_old_checksum_or_apk_tampering_fails(self):
        with self.apk.open("ab") as handle:
            handle.write(b"appended tamper")
        with self.assertRaisesRegex(ValueError, "SHA256SUMS"):
            self.verify()

    def test_missing_pin_and_different_apk_certificate_fail(self):
        with self.assertRaisesRegex(ValueError, "does not match expected"):
            self.verify(expected_signer="bb" * 32)
        report = self.output / "SIGNING_INFO.txt"
        report.write_text(report.read_text().replace("Mode: persistent", "Mode: ephemeral"))
        with self.assertRaisesRegex(ValueError, "report has not passed"):
            self.verify()

    def test_wrong_version_name_or_package_rejected(self):
        for bad in (
            AAPT_GOOD.replace("0.0.8", "0.0.9"),
            AAPT_GOOD.replace(PACKAGE, "org.fake.app"),
        ):
            with self.subTest(bad=bad):
                with patch("tools.android_release_gate.subprocess.run",
                           return_value=Mock(stdout=bad)):
                    with self.assertRaisesRegex(ValueError, "identity mismatch"):
                        verify_release(
                            self.output, expected_version=VERSION, source_root=self.source,
                            source_sha=SHA, git_ref="refs/heads/main", event="workflow_dispatch",
                            expected_signer=PIN, aapt="aapt",
                        )

    def test_wrong_sdk_or_missing_manifest_metadata_blocks(self):
        for bad in (
            AAPT_GOOD.replace("sdkVersion:'31'", "sdkVersion:'28'"),
            AAPT_GOOD.replace("targetSdkVersion:'35'", "targetSdkVersion:'30'"),
            AAPT_GOOD.replace("versionCode='8'", "versionCode='0'"),
        ):
            with self.subTest(bad=bad):
                with patch("tools.android_release_gate.subprocess.run",
                           return_value=Mock(stdout=bad)):
                    with self.assertRaises(ValueError):
                        verify_release(
                            self.output, expected_version=VERSION, source_root=self.source,
                            source_sha=SHA, git_ref="refs/heads/main", event="workflow_dispatch",
                            expected_signer=PIN, aapt="aapt",
                        )

    def test_reject_extra_credential_and_symlinked_report(self):
        injected = self.output / "debug.keystore"
        injected.write_bytes(b"DO_NOT_UPLOAD")
        with self.assertRaisesRegex(ValueError, "Incomplete or unexpected"):
            self.verify()
        injected.unlink()
        target = self.root / "report-elsewhere"
        target.write_text((self.output / "PROTECTION_INFO.txt").read_text())
        (self.output / "PROTECTION_INFO.txt").unlink()
        (self.output / "PROTECTION_INFO.txt").symlink_to(target)
        with self.assertRaisesRegex(ValueError, "Incomplete or unexpected"):
            self.verify()

    def test_v4_idsig_sidecar_is_detected_without_relaxing_release_inventory(self):
        # apksigner default v4 signatures can be generated next to the
        # short-lived signed APK; Phase09 must still reject any stray files.
        sidecar = self.output / ".lala-signed-synthetic.apk.idsig"
        sidecar.write_bytes(b"unwanted-v4-test-sidecar")
        with self.assertRaisesRegex(
            ValueError, "v4-sidecar-present=True"
        ) as error:
            self.verify()
        self.assertIn("unexpected-count=1", str(error.exception))
        self.assertNotIn(sidecar.name, str(error.exception))
        sidecar.unlink()
        self.assertEqual(self.verify()["apk"]["package"], PACKAGE)

    def test_phase09_reports_missing_trusted_evidence_without_exposing_extras(self):
        missing = self.output / "PRESPLASH_INFO.txt"
        missing.unlink()
        extra = self.output / "non-public-credential-test.txt"
        extra.write_text("synthetic only", encoding="utf-8")
        with self.assertRaisesRegex(
            ValueError, "missing=PRESPLASH_INFO.txt"
        ) as failure:
            self.verify()
        message = str(failure.exception)
        self.assertIn("unexpected-count=1", message)
        self.assertNotIn(extra.name, message)
        self.assertNotIn("synthetic only", message)

    def test_tag_and_manual_ref_guard_and_source_sha(self):
        with self.assertRaisesRegex(ValueError, "main"):
            self.verify(git_ref="refs/heads/feature")
        with self.assertRaisesRegex(ValueError, "tag does not match"):
            self.verify(event="push", git_ref="refs/tags/v0.0.9")
        self.assertEqual(
            self.verify(event="push", git_ref="refs/tags/v0.0.8")["source"]["git_ref"],
            "refs/tags/v0.0.8",
        )
        with self.assertRaisesRegex(ValueError, "SHA invalid"):
            self.verify(source_sha="not-a-commit")

    def test_refuses_wrong_source_version_and_double_publish(self):
        (self.source / "android_app/version.py").write_text("ANDROID_VERSION = '0.0.9'\n")
        with self.assertRaisesRegex(ValueError, "Version mismatch"):
            self.verify()
        (self.source / "android_app/version.py").write_text("ANDROID_VERSION = '0.0.8'\n")
        self.assertEqual(self.verify()["apk"]["version_name"], "0.0.8")
        with patch("tools.android_release_gate.subprocess.run",
                   return_value=Mock(stdout=AAPT_GOOD)):
            manifest = self.finalize()
        self.assertTrue(manifest.is_file())
        with self.assertRaisesRegex(ValueError, "already finalized"):
            self.finalize()

    def test_workflow_order_and_version_futureproofing(self):
        workflow = (ROOT / ".github/workflows/android-apk.yml").read_text(encoding="utf-8")
        self.assertNotIn('== "v0.0.8"', workflow)
        self.assertIn("os.environ[\"RELEASE_VERSION\"]", workflow)
        checks = [
            "python tools/android_native_cores.py stage",
            "python tools/android_signing.py resign",
            "python tools/android_native_wire.py report-apk",
            "python tools/android_native_vault.py report-apk",
            "python tools/android_native_cores.py report-apk",
            "python tools/android_signing.py report",
            "python tools/android_integrity.py report",
            "python tools/android_hardening.py report",
            'sha256sum "$output" > SHA256SUMS.txt',
            "python tools/android_release_gate.py android-output",
            "uses: actions/upload-artifact",
        ]
        positions = [workflow.index(item) for item in checks]
        self.assertEqual(positions, sorted(positions))
        self.assertNotIn("pull_request:", workflow)
        self.assertIn("secrets.ANDROID_DEBUG_KEYSTORE_BASE64", workflow)
        self.assertIn("vars.ANDROID_EXPECTED_SIGNER_SHA256", workflow)


if __name__ == "__main__":
    unittest.main()
