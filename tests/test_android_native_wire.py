"""Opt-in native-wire candidate must not weaken APK packaging safety."""
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

from tools.android_native_wire import SHIM, _is_exact_shim_bytecode, stage, verify_apk


class NativeWireTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.repo = self.base / "repo"
        self.repo.mkdir()
        (self.repo / "wlre/network").mkdir(parents=True)
        (self.repo / "p4a-recipes/lalawire").mkdir(parents=True)
        (self.repo / "wlre/network/wire.py").write_text(
            '"""Strict packet primitives and the server codec observed in EXP_Monitor."""\nX = 1\n',
            encoding="utf-8")
        (self.repo / "p4a-recipes/lalawire/__init__.py").write_text("recipe=1\n", encoding="utf-8")
        (self.repo / "p4a-recipes/lalawire/setup.py").write_text("setup()\n", encoding="utf-8")
        (self.repo / "buildozer.spec").write_text(
            "[app]\nsource.exclude_dirs = docs,tests,tools\nrequirements = python3,kivy\n"
            "p4a.branch = develop\nandroid.minapi = 31\nandroid.archs = arm64-v8a\n",
            encoding="utf-8")

    def test_stage_preserves_original_and_excludes_sensitive_source_from_app(self):
        output = self.base / "native"
        original = (self.repo / "wlre/network/wire.py").read_bytes()
        self.assertEqual(stage(self.repo, output), output)
        self.assertEqual((self.repo / "wlre/network/wire.py").read_bytes(), original)
        self.assertEqual((output / "wlre/network/wire.py").read_text(), SHIM)
        self.assertEqual(
            (output / "p4a-recipes/lalawire/src/_wlre_wire_native.pyx").read_bytes(),
            original,
        )
        self.assertEqual(
            (output / "p4a-recipes/lalawire/src/setup.py").read_text(),
            "setup()\n",
        )
        spec = (output / "buildozer.spec").read_text()
        self.assertIn("requirements = python3,kivy,lalawire", spec)
        self.assertIn(f"p4a.local_recipes = {output / 'p4a-recipes'}", spec)
        self.assertIn("source.exclude_dirs = p4a-recipes,docs", spec)
        self.assertIn("android.archs = arm64-v8a", spec)

    def test_refuse_to_overwrite_existing_or_in_tree_staging(self):
        with self.assertRaises(ValueError):
            stage(self.repo, self.repo / "native")
        self.assertFalse((self.repo / "native").exists())
        stage(self.repo, self.base / "native")
        with self.assertRaises(FileExistsError):
            stage(self.repo, self.base / "native")

    def test_deny_other_arch_before_creating_native_stage(self):
        path = self.repo / "buildozer.spec"
        path.write_text(path.read_text().replace("arm64-v8a", "x86_64"))
        with self.assertRaisesRegex(ValueError, "ARM64-only"):
            stage(self.repo, self.base / "native")
        self.assertFalse((self.base / "native").exists())

    def apk(self, inner, include_native=True, include_shim=True):
        path = self.base / "app.apk"
        buffer = io.BytesIO()
        valid_shim = (
            importlib.util.MAGIC_NUMBER + b"\x00" * 12
            + marshal.dumps(compile(SHIM, "wlre/network/wire.py", "exec"))
        )
        contents = ({"wlre/network/wire.pyc": valid_shim} if include_shim else {})
        contents.update(inner)
        with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
            for name, payload in contents.items():
                info = tarfile.TarInfo(name)
                info.size = len(payload)
                tar.addfile(info, io.BytesIO(payload))
        with zipfile.ZipFile(path, "w") as archive:
            if include_native:
                archive.writestr("lib/arm64-v8a/libpython3.11.so", b"stub")
            archive.writestr("assets/private.tar", buffer.getvalue())
        return path

    def elf(self, machine=183):
        payload = bytearray(64)
        payload[:7] = b"\x7fELF\x02\x01\x01"
        struct.pack_into("<H", payload, 16, 3)  # ET_DYN
        struct.pack_into("<H", payload, 18, machine)
        struct.pack_into("<I", payload, 20, 1)
        struct.pack_into("<H", payload, 52, 64)
        return bytes(payload)

    def test_arm64_elf_and_linux_binary_distinguished(self):
        path = self.apk({
            "site-packages/_wlre_wire_native.cpython-311-aarch64-linux-android.so":
                self.elf()
        })
        self.assertEqual(verify_apk(path)["verified_wire_shims"], 1)
        path = self.apk({
            "_wlre_wire_native.cpython-311-x86_64-linux-gnu.so": self.elf(62)
        })
        with self.assertRaisesRegex(ValueError, "Non-ARM64"):
            verify_apk(path)

    def test_apk_fails_closed_when_missing_or_leaking_native_module(self):
        with self.assertRaisesRegex(ValueError, "Missing Android ARM64 native"):
            verify_apk(self.apk({}))
        with self.assertRaisesRegex(ValueError, "leaks implementation"):
            verify_apk(self.apk({
                "_wlre_wire_native.so": self.elf(), "wlre/network/wire.py": b"secret"
            }))
        with self.assertRaisesRegex(ValueError, "leaks implementation"):
            verify_apk(self.apk({
                "_wlre_wire_native.so": self.elf(),
                "wlre/network/wire.pyc": b"Strict packet primitives and the server codec",
            }))
        with self.assertRaisesRegex(ValueError, "does not contain Android ARM64"):
            verify_apk(self.apk({"_wlre_wire_native.so": self.elf()}, include_native=False))

    def test_native_without_exact_shim_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Missing verified wire import shim"):
            verify_apk(self.apk({"_wlre_wire_native.so": self.elf()}, include_shim=False))
        old_module = compile(
            "class Reader: pass\nclass FrameDecoder: pass\n",
            "wlre/network/wire.py", "exec"
        )
        old_bytecode = importlib.util.MAGIC_NUMBER + b"\x00" * 12 + marshal.dumps(old_module)
        with self.assertRaisesRegex(ValueError, "unverified wire bytecode"):
            verify_apk(self.apk({
                "_wlre_wire_native.so": self.elf(),
                "wlre/network/__pycache__/wire.cpython-311.pyc": old_bytecode,
            }))

    def test_reject_host_binary_tag_even_with_arm64_header(self):
        with self.assertRaisesRegex(ValueError, "Non-ARM64"):
            verify_apk(self.apk({
                "_wlre_wire_native.cpython-311-x86_64-linux-gnu.so": self.elf(),
            }))

    def test_reject_trailing_payload_hidden_in_shim_bytecode(self):
        valid = (
            importlib.util.MAGIC_NUMBER + b"\x00" * 12
            + marshal.dumps(compile(SHIM, "wire.py", "exec"))
        )
        with self.assertRaisesRegex(ValueError, "unverified wire bytecode"):
            verify_apk(self.apk({
                "_wlre_wire_native.so": self.elf(),
                "wlre/network/wire.pyc": valid + b"secret trailing data",
            }))

    def test_native_bytecode_uses_matching_target_hostpython(self):
        valid = (
            importlib.util.MAGIC_NUMBER + b"\x00" * 12
            + marshal.dumps(compile(SHIM, "<shim>", "exec"))
        )
        self.assertTrue(_is_exact_shim_bytecode(valid))
        with patch("tools.android_native_wire.subprocess.run") as runner:
            runner.return_value.returncode = 0
            self.assertTrue(_is_exact_shim_bytecode(valid, pyc_python=self.base / "python3.14"))
            self.assertIn("_verify-pyc", runner.call_args.args[0])
            runner.return_value.returncode = 1
            self.assertFalse(_is_exact_shim_bytecode(valid, pyc_python=self.base / "python3.14"))
        self.assertFalse(_is_exact_shim_bytecode(b"wrong magic"))

    def test_weak_elf_header_is_rejected(self):
        broken = bytearray(self.elf())
        struct.pack_into("<H", broken, 16, 2)  # ET_EXEC, not a shared object
        with self.assertRaisesRegex(ValueError, "Non-ARM64"):
            verify_apk(self.apk({"_wlre_wire_native.so": bytes(broken)}))


if __name__ == "__main__":
    unittest.main()
