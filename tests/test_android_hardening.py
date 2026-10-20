"""Test the debug APK's real security boundaries, without distributing keys."""
from pathlib import Path
from io import BytesIO
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import subprocess
import sys

from tools.android_hardening import (
    check_apk, check_configuration, check_files, inspect_apk, report, ROOT,
)


def fixture(root, *, backup="False", excludes=None):
    for directory in ("android_app", "wlre", "tools"):
        (root / directory).mkdir(exist_ok=True)
    exclude = excludes or ".git,.github,tests,tools,.buildozer,bin"
    (root / "buildozer.spec").write_text(
        "[app]\nandroid.allow_backup = " + backup +
        "\nsource.dir = .\nsource.exclude_dirs = " + exclude +
        "\nandroid.minapi = 31\nandroid.archs = arm64-v8a\n",
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

    def test_minimum_sdk_and_single_arm64_target_are_pinned(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fixture(root)
            spec = root / "buildozer.spec"
            original = spec.read_text()
            spec.write_text(original.replace("android.minapi = 31", "android.minapi = 30"))
            with self.assertRaisesRegex(ValueError, "minimum API"):
                check_configuration(root)
            spec.write_text(original.replace("android.archs = arm64-v8a",
                                             "android.archs = arm64-v8a,armeabi-v7a"))
            with self.assertRaisesRegex(ValueError, "ARM64-only"):
                check_configuration(root)

    def test_main_entrypoint_does_not_leak_private_key_material(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fixture(root)
            marker = ("-----BEGIN " + "PRIVATE KEY-----")
            (root / "main.py").write_text("TEST = " + repr(marker))
            with self.assertRaisesRegex(ValueError, "main.py") as result:
                check_files(root)
            self.assertNotIn(marker, str(result.exception))

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

    @staticmethod
    def private_tar(entries):
        output = BytesIO()
        with tarfile.open(fileobj=output, mode="w:gz") as stream:
            for name, contents in entries.items():
                data = contents.encode() if isinstance(contents, str) else contents
                info = tarfile.TarInfo(name)
                info.size = len(data)
                stream.addfile(info, BytesIO(data))
        return output.getvalue()

    def test_hardening_report_runs_as_direct_script_and_package_module(self):
        """The APK workflow invokes 'python tools/android_hardening.py report'."""
        with tempfile.TemporaryDirectory() as temp:
            apk = Path(temp) / "demo.apk"
            with zipfile.ZipFile(apk, "w") as stream:
                stream.writestr("assets/private.tar", self.private_tar({
                    "wlre/network/wire.pyc": b"compiled",
                    "assets/config.json": b'{"feature":true}',
                }))
            for argv in (
                [str(ROOT / "tools" / "android_hardening.py"), "report", str(apk)],
                ["-m", "tools.android_hardening", "report", str(apk)],
            ):
                with self.subTest(argv=argv[0]):
                    executed = subprocess.run(
                        [sys.executable, *argv], cwd=ROOT,
                        capture_output=True, text=True, timeout=20,
                    )
                    self.assertEqual(
                        executed.returncode, 0,
                        "Archive audit failed in a supported invocation mode: "
                        + executed.stderr[-800:],
                    )
                    self.assertIn("Phase06 ZIP/TAR", (apk.parent / "PROTECTION_INFO.txt").read_text())

    def test_packaged_python_bytecode_is_reported_not_claimed_protected(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / "demo.apk"
            payload = self.private_tar({
                "android_app/app.pyc": b"compiled",
                "wlre/network/wire.pyc": b"compiled",
                "main.pyc": b"compiled",
            })
            with zipfile.ZipFile(archive, "w") as stream:
                stream.writestr("assets/private.tar", payload)
                stream.writestr("lib/arm64-v8a/libpython3.so", b"binary")
            result = inspect_apk(archive)
            self.assertEqual(result["python_bytecode"], 3)
            self.assertEqual(result["python_source"], 0)
            self.assertEqual(result["native_arm64_libraries"], 1)
            self.assertTrue(result["private_tar"])
            report_text = report(archive).read_text()
            self.assertIn("Bundled Python bytecode (.pyc/.pyo): 3", report_text)
            self.assertIn("bytecode can be extracted", report_text)
            self.assertNotIn("protected by Cython", report_text)

    def test_embedded_tar_rejects_hidden_signing_key(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / "demo.apk"
            with zipfile.ZipFile(archive, "w") as stream:
                stream.writestr("assets/private.tar",
                                self.private_tar({"android_app/hidden/release.keystore": b"dummy"}))
            with self.assertRaisesRegex(ValueError, "credential file"):
                check_apk(archive)

    def test_application_source_inside_apk_is_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            for path in ("android_app/vault.py", "wlre/network/wire.py", "main.py"):
                with self.subTest(path=path):
                    apk = Path(temp) / "demo.apk"
                    with zipfile.ZipFile(apk, "w") as stream:
                        stream.writestr("assets/private.tar",
                                        self.private_tar({path: "not compiled"}))
                    with self.assertRaisesRegex(ValueError, "Uncompiled application Python"):
                        check_apk(apk)

    def test_other_abi_libraries_are_not_accepted(self):
        with tempfile.TemporaryDirectory() as temp:
            apk = Path(temp) / "demo.apk"
            with zipfile.ZipFile(apk, "w") as stream:
                stream.writestr("lib/armeabi-v7a/libpython.so", b"bad target")
            with self.assertRaisesRegex(ValueError, "outside ARM64"):
                check_apk(apk)

    def test_embedded_archive_links_and_unsafe_paths_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            apk = Path(temp) / "demo.apk"
            linked = BytesIO()
            with tarfile.open(fileobj=linked, mode="w:gz") as archive:
                item = tarfile.TarInfo("wlre/network/wire.pyc")
                item.type = tarfile.SYMTYPE
                item.linkname = "external"
                archive.addfile(item)
            with zipfile.ZipFile(apk, "w") as stream:
                stream.writestr("assets/private.tar", linked.getvalue())
            with self.assertRaisesRegex(ValueError, "Linked members"):
                check_apk(apk)
            with zipfile.ZipFile(apk, "w") as stream:
                stream.writestr("assets/private.tar",
                                self.private_tar({"../main.pyc": b"unsafe"}))
            with self.assertRaisesRegex(ValueError, "Unsafe APK archive"):
                check_apk(apk)

    def test_report_exposes_high_risk_bytecode_without_claiming_cython(self):
        with tempfile.TemporaryDirectory() as temp:
            apk = Path(temp) / "demo.apk"
            with zipfile.ZipFile(apk, "w") as stream:
                stream.writestr("assets/private.tar", self.private_tar({
                    "android_app/vault.pyc": b"cipher logic",
                    "wlre/network/wire.pyc": b"packet logic",
                    "main.pyc": b"entry point",
                }))
            counts = inspect_apk(apk)
            self.assertEqual(counts["app_bytecode"], 3)
            self.assertEqual(counts["high_risk_bytecode"], 2)
            text = report(apk).read_text()
            self.assertIn("High-risk core bytecode still exposed: 2", text)
            self.assertIn("Cython ARM64 wire core: see NATIVE_WIRE_INFO.txt", text)
            self.assertIn("Phase05 P0/P1 core protection: see independent PHASE05_ALL_CORES_INFO.txt audit", text)

    def test_broken_embedded_tar_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / "demo.apk"
            with zipfile.ZipFile(archive, "w") as stream:
                stream.writestr("assets/private.tar", b"not a tar")
            with self.assertRaisesRegex(ValueError, "Unable to audit"):
                check_apk(archive)

    def test_protection_report_does_not_claim_reverse_engineering_prevention(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / "demo.apk"
            with zipfile.ZipFile(archive, "w") as stream:
                stream.writestr("classes.dex", b"dex\n")
            output = report(archive).read_text()
            self.assertIn("NOT enabled", output)
            self.assertIn("Repository visibility must be verified", output)
            self.assertIn("APK credential filename audit (including private.tar): PASSED", output)


if __name__ == "__main__":
    unittest.main()
