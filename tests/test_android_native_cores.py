"""All Phase05 P0/P1 cores must pass staged isolation + native APK audit."""
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

from tools.android_native_cores import (
    CORE_LIST, _exact_shim, _is_core_pyc, report_apk, shim, stage, verify_apk,
)


def pyc(s):
    return (importlib.util.MAGIC_NUMBER + bytes(12) +
            marshal.dumps(compile(s, "<core-shim>", "exec")))


def elf(architecture=183):
    blob = bytearray(64)
    blob[:7] = b"\x7fELF\x02\x01\x01"
    struct.pack_into("<H", blob, 16, 3)
    struct.pack_into("<H", blob, 18, architecture)
    struct.pack_into("<I", blob, 20, 1)
    struct.pack_into("<H", blob, 52, 64)
    return bytes(blob)


def tar(files):
    memory = io.BytesIO()
    with tarfile.open(fileobj=memory, mode="w:gz") as archive:
        for name, data in files.items():
            member = tarfile.TarInfo(name)
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
    return memory.getvalue()


class NativeCoreTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.source = self.root / "repo"
        for folder in ("p4a-recipes/lalawire", "p4a-recipes/lalavault",
                       "wlre/network", "android_app"):
            (self.source / folder).mkdir(parents=True, exist_ok=True)
        (self.source / "buildozer.spec").write_text(
            "[app]\nsource.exclude_dirs = tools,docs,tests\n"
            "requirements = python3,kivy\np4a.branch = develop\n"
            "android.minapi = 31\nandroid.archs = arm64-v8a\n", encoding="utf-8")
        (self.source / "wlre/network/wire.py").write_text(
            '"""Strict packet primitives and the server codec observed in EXP_Monitor."""\n'
            "class Reader: pass\n", encoding="utf-8")
        (self.source / "android_app/vault.py").write_text(
            '"""Android-private ciphertext store; AES key never leaves Android Keystore."""\n'
            "class AccountVault: pass\n", encoding="utf-8")
        for recipe in ("lalawire", "lalavault"):
            self.create_recipe(recipe)
        for rel, recipe, _, _ in CORE_LIST:
            (self.source / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.source / rel).write_text(
                '"""Synthetic test implementation; not a game implementation."""\n'
                "class Example: pass\n", encoding="utf-8")
            self.create_recipe(recipe)

    def create_recipe(self, recipe):
        folder = self.source / "p4a-recipes" / recipe
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "__init__.py").write_text("recipe = True\n")
        (folder / "setup.py").write_text("setup()\n")

    def test_complete_8_core_staging_without_touching_checkout(self):
        originals = {rel: (self.source / rel).read_bytes()
                     for rel, _, _, _ in CORE_LIST}
        original_wire = (self.source / "wlre/network/wire.py").read_bytes()
        output = stage(self.source, self.root / "native")
        for rel, recipe, extension, _ in CORE_LIST:
            self.assertEqual((self.source / rel).read_bytes(), originals[rel])
            self.assertEqual((output / rel).read_text(), shim(extension))
            self.assertEqual((output / "p4a-recipes" / recipe / "src" /
                              (extension + ".pyx")).read_bytes(), originals[rel])
            self.assertTrue((output / "p4a-recipes" / recipe / "__init__.py").exists())
            self.assertTrue((output / "p4a-recipes" / recipe / "src/setup.py").exists())
        self.assertEqual((self.source / "wlre/network/wire.py").read_bytes(), original_wire)
        requirement = next(line for line in
                           (output / "buildozer.spec").read_text().splitlines()
                           if line.startswith("requirements = "))
        self.assertIn(",lalawire,lalavault", requirement)
        for _, recipe, _, _ in CORE_LIST:
            self.assertIn("," + recipe, requirement)
        self.assertEqual(len(CORE_LIST), 6)

    def test_all_stage_fail_closed_when_missing_core_or_bad_target(self):
        rel = CORE_LIST[0][0]
        (self.source / rel).unlink()
        with self.assertRaisesRegex(ValueError, "Missing"):
            stage(self.source, self.root / "native")
        self.assertFalse((self.root / "native").exists())

    def test_refuse_stage_overwrite_and_nested_destination(self):
        with self.assertRaisesRegex(ValueError, "outside"):
            stage(self.source, self.source / "nested")
        stage(self.source, self.root / "native")
        with self.assertRaises(FileExistsError):
            stage(self.source, self.root / "native")

    def apk(self, *, additional_source=None, binary_overrides=None):
        src = {rel[:-3] + ".pyc": pyc(shim(extension))
               for rel, _, extension, _ in CORE_LIST}
        src.update(additional_source or {})
        native = {"_python_bundle/site-packages/" + extension + ".so": elf()
                  for _, _, extension, _ in CORE_LIST}
        native.update(binary_overrides or {})
        path = self.root / "test.apk"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("assets/private.tar", tar(src))
            archive.writestr("lib/arm64-v8a/libpybundle.so", tar(native))
        return path

    @patch("tools.android_native_cores.verify_vault_apk")
    def test_full_six_core_apk_and_existing_wire_vault_gate(self, previous):
        result = verify_apk(self.apk())
        previous.assert_called_once()
        self.assertEqual(len(result["native_cores"]), 6)
        self.assertTrue(all(n == 1 for n in result["verified_shims"].values()))
        report = report_apk(self.root / "test.apk")
        self.assertIn("P0/P1 Cython audit", report.read_text())
        self.assertIn("Python implementations of these six cores exposed: 0",
                      report.read_text())

    @patch("tools.android_native_cores.verify_vault_apk")
    def test_refuse_missing_native_source_leaks_and_wrong_abi(self, previous):
        rel, _, ext, _ = CORE_LIST[0]
        native_file = "_python_bundle/site-packages/" + ext + ".so"
        with self.assertRaisesRegex(ValueError, "Non-ARM64"):
            verify_apk(self.apk(binary_overrides={native_file: b"garbage"}))
        with self.assertRaisesRegex(ValueError, "implementation leaked"):
            verify_apk(self.apk(additional_source={rel: b"private implementation"}))
        with self.assertRaisesRegex(ValueError, "Non-ARM64"):
            verify_apk(self.apk(binary_overrides={native_file: elf(62)}))

    @patch("tools.android_native_cores.verify_vault_apk")
    def test_refuse_altered_pyc_and_hidden_native_source(self, previous):
        rel, _, ext, _ = CORE_LIST[-1]
        with self.assertRaisesRegex(ValueError, "implementation leaked"):
            verify_apk(self.apk(additional_source={rel[:-3] + ".pyc":
                                                  pyc("def implementation(): pass")}))
        with self.assertRaisesRegex(ValueError, "implementation leaked"):
            verify_apk(self.apk(binary_overrides={
                "_python_bundle/site-packages/" + ext + ".pyx": b"native source"
            }))

    def test_correct_shim_requires_matching_magic_and_no_extra_bytes(self):
        rel, _, ext, _ = CORE_LIST[1]
        self.assertTrue(_is_core_pyc(rel[:-3] + ".pyc", rel))
        self.assertTrue(_is_core_pyc(str(Path(rel).parent / "__pycache__" /
                                      (Path(rel).stem + ".cpython-314.pyc")), rel))
        self.assertTrue(_exact_shim(pyc(shim(ext)), ext))
        self.assertFalse(_exact_shim(pyc(shim(ext)) + b"hidden", ext))
        self.assertFalse(_exact_shim(b"not a valid pyc", ext))
        with patch("tools.android_native_cores.subprocess.run") as process:
            process.return_value.returncode = 0
            self.assertTrue(_exact_shim(pyc(shim(ext)), ext,
                                        pyc_python=self.root / "python3.14"))
            self.assertIn("_verify-core-pyc", process.call_args.args[0])
            process.return_value.returncode = 1
            self.assertFalse(_exact_shim(pyc(shim(ext)), ext,
                                         pyc_python=self.root / "python3.14"))


if __name__ == "__main__":
    unittest.main()
