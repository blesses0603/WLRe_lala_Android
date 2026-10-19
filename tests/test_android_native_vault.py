"""Phase05 vault pilot staging, native ABI, exact-shim and leakage regressions."""
import importlib.util
import io
import marshal
from pathlib import Path
import struct
import tarfile
import tempfile
import unittest
import zipfile
from unittest.mock import patch

from tools.android_native_wire import SHIM as WIRE_SHIM
from tools.android_native_vault import SHIM, _exact_shim, stage, verify_apk, report_apk


def pyc(source, name):
    return (importlib.util.MAGIC_NUMBER + bytes(12)
            + marshal.dumps(compile(source, name, "exec")))


def tarball(entries):
    memory = io.BytesIO()
    with tarfile.open(fileobj=memory, mode="w:gz") as archive:
        for name, data in entries.items():
            entry = tarfile.TarInfo(name)
            entry.size = len(data)
            archive.addfile(entry, io.BytesIO(data))
    return memory.getvalue()


def elf(arch=183):
    data = bytearray(64)
    data[:7] = b"\x7fELF\x02\x01\x01"
    struct.pack_into("<H", data, 16, 3)
    struct.pack_into("<H", data, 18, arch)
    struct.pack_into("<I", data, 20, 1)
    struct.pack_into("<H", data, 52, 64)
    return bytes(data)


class AndroidNativeVaultTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.source = self.root / "project"
        for directory in ("wlre/network", "android_app",
                          "p4a-recipes/lalawire", "p4a-recipes/lalavault"):
            (self.source / directory).mkdir(parents=True, exist_ok=True)
        (self.source / "wlre/network/wire.py").write_text(
            '"""Strict packet primitives and the server codec observed in EXP_Monitor."""\n'
            "class Reader: pass\n", encoding="utf-8")
        (self.source / "android_app/vault.py").write_text(
            '"""Android-private ciphertext store; AES key never leaves Android Keystore."""\n'
            "class AccountVault: pass\n", encoding="utf-8")
        for recipe in ("lalawire", "lalavault"):
            (self.source / "p4a-recipes" / recipe / "__init__.py").write_text(
                "recipe=1\n", encoding="utf-8")
            (self.source / "p4a-recipes" / recipe / "setup.py").write_text(
                "setup()\n", encoding="utf-8")
        (self.source / "buildozer.spec").write_text(
            "[app]\nsource.exclude_dirs = tools,tests,docs\n"
            "requirements = python3,kivy\n"
            "p4a.branch = develop\nandroid.minapi = 31\n"
            "android.archs = arm64-v8a\n", encoding="utf-8")

    def test_stage_keeps_project_python_and_wire_unchanged(self):
        original_vault = (self.source / "android_app/vault.py").read_bytes()
        original_wire = (self.source / "wlre/network/wire.py").read_bytes()
        output = stage(self.source, self.root / "native")
        self.assertEqual((self.source / "android_app/vault.py").read_bytes(), original_vault)
        self.assertEqual((self.source / "wlre/network/wire.py").read_bytes(), original_wire)
        self.assertEqual((output / "android_app/vault.py").read_text(), SHIM)
        self.assertEqual((output / "p4a-recipes/lalavault/src/_wlre_vault_native.pyx").read_bytes(),
                         original_vault)
        self.assertEqual((output / "wlre/network/wire.py").read_text(), WIRE_SHIM)
        spec = (output / "buildozer.spec").read_text()
        self.assertIn("requirements = python3,kivy,lalawire,lalavault", spec)
        self.assertIn("source.exclude_dirs = p4a-recipes,", spec)
        self.assertIn("p4a.local_recipes = ", spec)

    def test_missing_recipe_or_modified_vault_rejected_before_stage(self):
        (self.source / "p4a-recipes/lalavault/setup.py").unlink()
        with self.assertRaisesRegex(ValueError, "Missing"):
            stage(self.source, self.root / "native")
        self.assertFalse((self.root / "native").exists())

    def test_reject_in_tree_and_overwrite_stage(self):
        with self.assertRaisesRegex(ValueError, "outside"):
            stage(self.source, self.source / "staged")
        stage(self.source, self.root / "native")
        with self.assertRaises(FileExistsError):
            stage(self.source, self.root / "native")

    def apk(self, *, app=None, bundle=None):
        application = {
            "wlre/network/wire.pyc": pyc(WIRE_SHIM, "wlre/network/wire.py"),
            "android_app/vault.pyc": pyc(SHIM, "android_app/vault.py"),
        }
        if app:
            application.update(app)
        native = {
            "site-packages/_wlre_wire_native.so": elf(),
            "site-packages/_wlre_vault_native.so": elf(),
        }
        if bundle:
            native.update(bundle)
        path = self.root / "candidate.apk"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("lib/arm64-v8a/libpython3.14.so", b"stub")
            archive.writestr("assets/private.tar", tarball(application))
            archive.writestr("lib/arm64-v8a/libpybundle.so", tarball(native))
        return path

    def test_verified_arm64_vault_and_existing_wire(self):
        proof = verify_apk(self.apk())
        self.assertEqual(proof["verified_vault_shims"], 1)
        self.assertEqual(len(proof["arm64_vault_extensions"]), 1)
        report = report_apk(self.root / "candidate.apk")
        self.assertIn("ARM64 Cython extension VERIFIED", report.read_text())
        self.assertIn("Original vault Python implementation source/bytecode leaks: 0",
                      report.read_text())

    def test_reject_wrong_abi(self):
        with self.assertRaisesRegex(ValueError, "Non-ARM64 native vault"):
            verify_apk(self.apk(bundle={"site-packages/_wlre_vault_native.so": elf(62)}))

    def test_reject_source_leakage(self):
        with self.assertRaisesRegex(ValueError, "leaks implementation"):
            verify_apk(self.apk(app={"android_app/vault.py": b"private logic"}))
        with self.assertRaisesRegex(ValueError, "leaks implementation"):
            verify_apk(self.apk(bundle={"site-packages/_wlre_vault_native.pyx": b"private logic"}))

    def test_reject_unverified_bytecode_and_fake_shim(self):
        with self.assertRaisesRegex(ValueError, "unverified vault bytecode"):
            verify_apk(self.apk(app={"android_app/vault.pyc":
                                    pyc("class AccountVault: pass", "vault.py")}))
        with self.assertRaisesRegex(ValueError, "unverified vault bytecode"):
            verify_apk(self.apk(app={"android_app/vault.pyc":
                                    pyc(SHIM, "vault.py") + b"append-secret"}))

    def test_missing_native_or_shim_rejected(self):
        with self.assertRaisesRegex(ValueError, "Expected one importable"):
            verify_apk(self.apk(bundle={"site-packages/_wlre_vault_native.so": b"garbage"}))
        with self.assertRaisesRegex(ValueError, "Expected one importable"):
            verify_apk(self.apk(app={"android_app/vault.pyc": pyc("", "vault.py")}))
    def test_refuse_host_binary_even_if_fake_elf_header(self):
        with self.assertRaisesRegex(ValueError, "Non-ARM64"):
            verify_apk(self.apk(bundle={
                "site-packages/_wlre_vault_native.cpython-311-x86_64-linux-gnu.so": elf()
            }))
    def test_exact_bytecode_requires_python_magic_and_no_trailing_data(self):
        good = pyc(SHIM, "vault.py")
        self.assertTrue(_exact_shim(good))
        self.assertFalse(_exact_shim(good + b"x"))
        self.assertFalse(_exact_shim(b"wrong"))
        with patch("tools.android_native_vault.subprocess.run") as proc:
            proc.return_value.returncode = 0
            self.assertTrue(_exact_shim(good, pyc_python=self.root / "hostpython3.14"))
            self.assertIn("_verify-vault-pyc", proc.call_args.args[0])
            proc.return_value.returncode = 1
            self.assertFalse(_exact_shim(good, pyc_python=self.root / "hostpython3.14"))


if __name__ == "__main__":
    unittest.main()
