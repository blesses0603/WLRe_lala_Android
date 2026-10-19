"""Phase07 runtime Android APK signature identity checks without signing secrets."""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from unittest.mock import patch

from android_app.integrity import IntegrityRejected, require_integrity, verify
from tools.android_integrity import (
    PACKAGE, PLACEHOLDER, RELATIVE_JAVA, pin_stage, verify_stage, report,
    verify_compiled_guard,
)

ROOT = Path(__file__).resolve().parents[1]
PIN = hashlib.sha256(b"synthetic-public-certificate").hexdigest()


class StagePinTests(unittest.TestCase):
    def setUp(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.root = Path(td.name)
        self.source = self.root / "source"
        self.stage = self.root / "disposable"
        self.source.mkdir()
        self.stage.mkdir()
        self.guard = self.stage / RELATIVE_JAVA
        self.guard.parent.mkdir(parents=True)
        self.guard.write_bytes((ROOT / RELATIVE_JAVA).read_bytes())

    def test_only_disposable_stage_receives_public_pin(self):
        before = (ROOT / RELATIVE_JAVA).read_bytes()
        pin_stage(self.stage, ":".join(PIN[n:n+2] for n in range(0, 64, 2)), source=self.source)
        self.assertTrue(verify_stage(self.stage, PIN))
        self.assertEqual(before, (ROOT / RELATIVE_JAVA).read_bytes())
        self.assertEqual(self.guard.read_text().count(PIN), 1)
        self.assertNotIn(PLACEHOLDER, self.guard.read_text())
        output = self.root / "output"
        output.mkdir()
        with zipfile.ZipFile(output / "test.apk", "w") as package:
            package.writestr("classes.dex", b"dex\\n035\\0" + PIN.encode("ascii"))
        info = report(output, self.stage, PIN).read_text()
        self.assertIn("Compiled APK DEX contains runtime signer pin: VERIFIED", info)
        self.assertIn("NOT VERIFIED", info)
        self.assertNotIn(PIN, info)

    def test_reject_missing_or_malformed_pin(self):
        for sample in ("", "a" * 62, "nothex", "f" * 65):
            with self.subTest(sample=sample):
                with self.assertRaises(ValueError):
                    pin_stage(self.stage, sample, source=self.source)
        self.assertIn(PLACEHOLDER, self.guard.read_text())

    def test_refuse_source_in_place_and_double_pin(self):
        with self.assertRaisesRegex(ValueError, "outside"):
            pin_stage(self.source, PIN, source=self.source)
        pin_stage(self.stage, PIN, source=self.source)
        with self.assertRaisesRegex(ValueError, "missing or duplicated"):
            pin_stage(self.stage, PIN, source=self.source)
        with self.assertRaisesRegex(ValueError, "differs"):
            verify_stage(self.stage, "f" * 64)

    def test_reject_symlink_and_wrong_package(self):
        self.guard.unlink()
        target = self.root / "target.java"
        target.write_bytes((ROOT / RELATIVE_JAVA).read_bytes())
        self.guard.symlink_to(target)
        with self.assertRaisesRegex(ValueError, "not staged"):
            pin_stage(self.stage, PIN, source=self.source)
        self.guard.unlink()
        self.guard.write_text(target.read_text().replace(PACKAGE, "org.different.name"))
        with self.assertRaisesRegex(ValueError, "package identifier mismatch"):
            pin_stage(self.stage, PIN, source=self.source)

    def test_compiled_apk_must_contain_public_certificate_pin_in_dex(self):
        apk = self.root / "compiled.apk"
        with zipfile.ZipFile(apk, "w") as package:
            package.writestr("classes.dex", b"irrelevant-bytecode")
        with self.assertRaisesRegex(ValueError, "lacks Phase07"):
            verify_compiled_guard(apk, PIN)
        with zipfile.ZipFile(apk, "w") as package:
            package.writestr("classes.dex", PLACEHOLDER.encode() + PIN.encode())
        with self.assertRaisesRegex(ValueError, "placeholder"):
            verify_compiled_guard(apk, PIN)
        with zipfile.ZipFile(apk, "w") as package:
            package.writestr("classes2.dex", PIN.encode())
        self.assertTrue(verify_compiled_guard(apk, PIN))

    def test_absent_environment_pin_fails_closed(self):
        with patch.dict(os.environ, {"ANDROID_EXPECTED_SIGNER_SHA256": ""}):
            with self.assertRaises(ValueError):
                pin_stage(self.stage, source=self.source)
        self.assertIn(PLACEHOLDER, self.guard.read_text())


class RuntimeGateTests(unittest.TestCase):
    class FakeGuard:
        def __init__(self, result):
            self.result = result
        def status(self, context):
            return self.result

    def loader(self, status):
        return lambda cls: self.FakeGuard(status)

    def test_match_allows_and_other_statuses_block_with_generic_reason(self):
        self.assertTrue(require_integrity(object(), loader=self.loader("OK")))
        for code in ("UNPINNED", "SIGNER_MISMATCH", "PACKAGE_MISMATCH",
                     "VERIFY_FAILED", "MULTIPLE_OR_MISSING_SIGNERS", None):
            with self.subTest(code=code):
                with self.assertRaisesRegex(IntegrityRejected, "A07") as err:
                    require_integrity(object(), loader=self.loader(code))
                self.assertNotIn(str(code), str(err.exception))
                self.assertEqual(verify(object(), loader=self.loader(code)), "REJECTED")

    def test_pyjnius_lookup_failure_is_sanitized_and_closed(self):
        def crash(_):
            raise RuntimeError("DO_NOT_LOG_PRIVATE_ACCOUNT")
        with self.assertRaises(IntegrityRejected) as err:
            require_integrity(object(), loader=crash)
        self.assertNotIn("DO_NOT_LOG_PRIVATE_ACCOUNT", str(err.exception))

    def test_both_processes_and_release_workflow_are_gated(self):
        activity = (ROOT / "android_app/app.py").read_text()
        service = (ROOT / "android_app/service.py").read_text()
        native_service = (ROOT / "android_app/java/org/lala/client/ConnectionService.java").read_text()
        workflow = (ROOT / ".github/workflows/android-apk.yml").read_text()
        self.assertLess(activity.index("require_integrity(activity)"),
                        activity.index("service.start(activity, '')"))
        self.assertLess(activity.index("require_integrity(activity)"),
                        activity.index("cipher = AndroidCipher()"))
        self.assertLess(service.index("require_integrity(service)"),
                        service.index("wake = power.newWakeLock"))
        self.assertLess(native_service.index("RuntimeIntegrity.status(this)"),
                        native_service.index("super.onStartCommand"))
        self.assertLess(workflow.index("python tools/android_integrity.py prepare-stage"),
                        workflow.index("secrets.ANDROID_DEBUG_KEYSTORE_BASE64"))
        self.assertLess(workflow.index("python tools/android_signing.py report"),
                        workflow.index("python tools/android_integrity.py report"))
        self.assertIn("android.add_src = android_app/java", (ROOT / "buildozer.spec").read_text())

    @unittest.skipUnless(shutil.which("javac"), "JDK required to syntax-check Java guard")
    def test_android_java_signer_verifier_compiles_against_android_api_shape(self):
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            stubs = {
                "android/content/Context.java": (
                    "package android.content;\n"
                    "import android.content.pm.PackageManager;\n"
                    "public class Context { public String getPackageName(){return \"org.lala.client.wlrelala\";} "
                    "public PackageManager getPackageManager(){return new PackageManager();} }\n"
                ),
                "android/content/pm/PackageManager.java": (
                    "package android.content.pm;\n"
                    "public class PackageManager { public static final int GET_SIGNING_CERTIFICATES=134217728; public static Signature[] signatures; public static boolean multiple; public static boolean crash; "
                    "public PackageInfo getPackageInfo(String p,int flags){if(crash) throw new RuntimeException(); PackageInfo info=new PackageInfo(); info.signingInfo=new SigningInfo(); return info;} }\n"
                ),
                "android/content/pm/PackageInfo.java": (
                    "package android.content.pm;\n"
                    "public class PackageInfo { public SigningInfo signingInfo; }\n"
                ),
                "android/content/pm/SigningInfo.java": (
                    "package android.content.pm;\n"
                    "public class SigningInfo { public boolean hasMultipleSigners(){return PackageManager.multiple;} "
                    "public Signature[] getApkContentsSigners(){return PackageManager.signatures;} }\n"
                ),
                "android/content/pm/Signature.java": (
                    "package android.content.pm;\n"
                    "public class Signature { private final byte[] bytes; public Signature(byte[] data){this.bytes=data;} public byte[] toByteArray(){return bytes;} }\n"
                ),
                "android/os/Build.java": (
                    "package android.os;\n"
                    "public class Build { public static class VERSION { public static int SDK_INT=35; } "
                    "public static class VERSION_CODES {public static final int P=28;} }\n"
                ),
            }
            source = []
            for filename, text in stubs.items():
                path = temp / filename
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text)
                source.append(str(path))
            guard = temp / "org/lala/client/RuntimeIntegrity.java"
            guard.parent.mkdir(parents=True)
            guard.write_text((ROOT / RELATIVE_JAVA).read_text().replace(PLACEHOLDER, PIN))
            source.append(str(guard))
            harness = temp / "SignerCases.java"
            harness.write_text("""
import android.content.Context;
import android.content.pm.PackageManager;
import android.content.pm.Signature;
import org.lala.client.RuntimeIntegrity;
public final class SignerCases {
    static void require(String expected, Context ctx) {
        String actual = RuntimeIntegrity.status(ctx);
        if (!expected.equals(actual)) throw new RuntimeException(expected + " != " + actual);
    }
    public static void main(String[] args) throws Exception {
        PackageManager.signatures = new Signature[] {
            new Signature("synthetic-public-certificate".getBytes("UTF-8")) };
        require("OK", new Context());
        PackageManager.signatures = new Signature[] {
            new Signature("different-certificate".getBytes("UTF-8")) };
        require("SIGNER_MISMATCH", new Context());
        PackageManager.signatures = new Signature[] {
            new Signature("synthetic-public-certificate".getBytes("UTF-8")),
            new Signature("different-certificate".getBytes("UTF-8")) };
        require("MULTIPLE_OR_MISSING_SIGNERS", new Context());
        PackageManager.signatures = new Signature[] {
            new Signature("synthetic-public-certificate".getBytes("UTF-8")) };
        PackageManager.multiple = true;
        require("MULTIPLE_OR_MISSING_SIGNERS", new Context());
        PackageManager.multiple = false;
        require("PACKAGE_MISMATCH", new Context() {
            @Override public String getPackageName() {return "org.fake.package";}
        });
        PackageManager.crash = true;
        require("VERIFY_FAILED", new Context());
        PackageManager.crash = false;
        android.os.Build.VERSION.SDK_INT = 27;
        require("UNSUPPORTED_API", new Context());
    }
}
""", encoding="utf-8")
            source.append(str(harness))
            result = subprocess.run(
                ["javac", "-d", str(temp / "classes"), *source],
                capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stderr[:1000])
            run = subprocess.run(
                ["java", "-cp", str(temp / "classes"), "SignerCases"],
                capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(run.returncode, 0, run.stderr[:1000])


if __name__ == "__main__":
    unittest.main()
