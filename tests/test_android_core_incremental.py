"""P3 eight independent SHA-256 native core caches: offline security gates."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
from pathlib import Path
import struct
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from tools.android_core_incremental import (
    CORES, CACHE_REL, INSTALL_REL, PLAN_REL, keys, plan, prepare, save,
)

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/android-apk.yml"
TOOLS = {"buildozer": "1.5.0", "Cython": "3.0.12"}


def arm64():
    result = bytearray(64)
    result[:7] = b"\x7fELF\x02\x01\x01"
    struct.pack_into("<H", result, 16, 3)
    struct.pack_into("<H", result, 18, 183)
    struct.pack_into("<I", result, 20, 1)
    struct.pack_into("<H", result, 52, 64)
    return bytes(result)


class P3NativeCoreCacheTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.stage = self.root / "stage"
        self.stage.mkdir()
        helper = self.stage / "p4a-recipes/lala_core_incremental.py"
        helper.parent.mkdir(parents=True)
        helper.write_bytes((ROOT / "p4a-recipes/lala_core_incremental.py").read_bytes())
        for name, ext in CORES:
            folder = self.stage / "p4a-recipes" / name
            (folder / "src").mkdir(parents=True)
            (folder / "__init__.py").write_text("recipe = 1\n", encoding="utf-8")
            (folder / "src/setup.py").write_text("setup()\n", encoding="utf-8")
            (folder / "src" / (ext + ".pyx")).write_text(
                "def native(): return 1\n", encoding="utf-8")

    def args(self):
        return {"image_version": "20261103.1", "tool_versions": TOOLS}

    def compiled(self):
        dest = self.stage / INSTALL_REL / "testdist/arm64-v8a"
        dest.mkdir(parents=True, exist_ok=True)
        for _, ext in CORES:
            (dest / (ext + ".cpython-314-aarch64-linux-android.so")).write_bytes(arm64())
        return dest

    def test_per_core_keys_are_exact_and_app_patch_not_an_input(self):
        self.assertEqual(len(CORES), 8)
        first = keys(self.stage, **self.args())
        self.assertEqual(len(first), 8)
        self.assertEqual(first, keys(self.stage, **self.args()))
        self.assertTrue(all(len(v) == 64 for v in first.values()))
        target = "lalasessions"
        file = self.stage / "p4a-recipes" / target / "src/_wlre_sessions_native.pyx"
        file.write_text("def native(): return 2\n", encoding="utf-8")
        second = keys(self.stage, **self.args())
        self.assertEqual({name for name in first if first[name] != second[name]},
                         {target})
        self.assertNotEqual(keys(self.stage, image_version="20261104.1",
                                 tool_versions=TOOLS), second)

    def test_unknown_runner_disables_p3_without_bypassing_build(self):
        self.assertFalse(plan(self.stage, image_version="", tool_versions=TOOLS)["enabled"])
        self.assertEqual(prepare(self.stage, image_version="",
                                 tool_versions=TOOLS)["hits"], [])
        self.assertEqual(json.loads((self.stage / PLAN_REL).read_text())["keys"], {})

    def test_saving_eight_elf_and_second_run_reuses_all(self):
        self.compiled()
        result = save(self.stage, **self.args())
        self.assertEqual(len(result["saved"]), 8)
        for recipe, ext in CORES:
            folder = self.stage / CACHE_REL / recipe
            receipt = json.loads((folder / "receipt.json").read_text())
            self.assertEqual(receipt["size"], 64)
            self.assertTrue((folder / receipt["filename"]).is_file())
        ready = prepare(self.stage, **self.args())
        self.assertEqual(len(ready["hits"]), 8)
        self.assertEqual(ready["misses"], [])
        self.assertEqual(save(self.stage, **self.args())["saved"], [])

    def test_changed_recipe_invalidates_only_one_core(self):
        self.compiled()
        save(self.stage, **self.args())
        recipe = "lalaclient"
        path = self.stage / "p4a-recipes" / recipe / "__init__.py"
        path.write_text("recipe = 2\n", encoding="utf-8")
        result = prepare(self.stage, **self.args())
        self.assertEqual(result["misses"], [recipe])
        self.assertEqual(len(result["hits"]), 7)
        self.assertFalse((self.stage / CACHE_REL / recipe).exists())

    def test_tampered_binary_and_bad_elf_are_misses(self):
        self.compiled()
        save(self.stage, **self.args())
        recipe = "lalavault"
        folder = self.stage / CACHE_REL / recipe
        receipt = json.loads((folder / "receipt.json").read_text())
        native = folder / receipt["filename"]
        native.write_bytes(b"X" + native.read_bytes()[1:])
        result = prepare(self.stage, **self.args())
        self.assertEqual(result["misses"], [recipe])
        self.assertFalse(folder.exists())
        self.compiled()
        target = self.stage / INSTALL_REL / "testdist/arm64-v8a/_wlre_vault_native.cpython-314-aarch64-linux-android.so"
        target.write_bytes(b"not an Android ELF")
        with self.assertRaisesRegex(ValueError, "AArch64 ELF"):
            save(self.stage, **self.args())

    def test_p4a_reuse_copies_exact_verified_elf_to_install_dir(self):
        self.compiled()
        save(self.stage, **self.args())
        prepare(self.stage, **self.args())
        fake = types.ModuleType("pythonforandroid")
        recipe_pkg = types.ModuleType("pythonforandroid.recipe")
        class Recipe:
            def build_arch(self, arch):
                self.base_called = True
        recipe_pkg.Recipe = Recipe
        path = ROOT / "p4a-recipes/lala_core_incremental.py"
        spec = importlib.util.spec_from_file_location("_test_lala_p3", path)
        module = importlib.util.module_from_spec(spec)
        installed = self.root / "site"
        class Context:
            def get_python_install_dir(self, arch):
                self_arch = arch
                return installed
        extension = "_wlre_vault_native"
        native = Recipe()
        native.name = "lalavault"
        native.site_packages_name = extension
        native.ctx = Context()
        with patch.dict(sys.modules, {"pythonforandroid": fake,
                                      "pythonforandroid.recipe": recipe_pkg}):
            spec.loader.exec_module(module)
        with patch.dict("os.environ", {
            "LALA_P3_CORE_CACHE": str(self.stage / CACHE_REL),
            "LALA_P3_CORE_PLAN": str(self.stage / PLAN_REL),
        }):
            self.assertTrue(module.reuse(native, types.SimpleNamespace(arch="arm64-v8a")))
            self.assertTrue(native.base_called)
            self.assertEqual(len(list(installed.glob(extension + "*.so"))), 1)
            self.assertFalse(module.reuse(native, types.SimpleNamespace(arch="x86_64")))

    def test_cli_import_is_executable_from_ci_worktree(self):
        # Run the real command, not a mocked import. Previously executing the
        # tools/ file directly crashed with ModuleNotFoundError: tools.
        output = self.root / "github-output.txt"
        env = os.environ.copy()
        env.pop("ImageVersion", None)
        env["GITHUB_OUTPUT"] = str(output)
        command = [sys.executable, "-m", "tools.android_core_incremental",
                   "plan", "--stage", str(self.stage)]
        completed = subprocess.run(
            command, cwd=ROOT, env=env, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("P3 independent core SHA-256 keys: 0", completed.stdout)
        self.assertIn("enabled=false", output.read_text(encoding="utf-8"))

    def test_workflow_has_eight_separate_exact_caches_after_signed_gate(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("LALA_P3_CORE_CACHE:", text)
        self.assertIn("LALA_P3_CORE_PLAN:", text)
        # All three CLI entry points must use the module form, so absolute
        # imports from tools work under the GitHub Actions runner.
        self.assertIn("python -m tools.android_core_incremental plan", text)
        self.assertIn("python -m tools.android_core_incremental prepare", text)
        self.assertIn("python -m tools.android_core_incremental save", text)
        self.assertNotIn("python tools/android_core_incremental.py", text)
        for recipe, _ in CORES:
            self.assertEqual(text.count("Restore P3 " + recipe + " verified"), 1)
            self.assertEqual(text.count("Save P3 " + recipe + " verified"), 1)
            self.assertEqual(text.count("lala-p3-core-v1-${{ runner.os }}-${{ runner.arch }}-${{ steps.p3_keys.outputs." + recipe + " }}"), 2)
            self.assertEqual(text.count("${{ env.LALA_P3_CORE_CACHE }}/" + recipe + "\n"), 2)
        p3_restore = text.index("Compute P3 SHA-256 keys")
        signing = text.index("Pin public signer into")
        build = text.index("buildozer -v android debug")
        gate = text.index("python tools/android_release_gate.py")
        snapshot = text.index("Snapshot verified P3 native extensions")
        save_first = text.index("Save P3 lalawire")
        upload = text.index("Upload APK (only after successful build)")
        self.assertTrue(p3_restore < signing < build < gate < snapshot < save_first < upload)
        self.assertNotIn("restore-keys:", text[p3_restore:signing])
        self.assertEqual(text.count("Save P3 "), 8)
        self.assertEqual(text.count("Restore P3 "), 8)


if __name__ == "__main__":
    unittest.main()
