"""Regression coverage for the source-only TPK dependency used by UnityPy."""
import importlib.util
from pathlib import Path
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class TpkArRecipeTests(unittest.TestCase):
    def setUp(self):
        # Only the p4a context is stubbed; execute the real local recipe's
        # build_arch against real source/install directories.
        module = ModuleType("pythonforandroid.recipe")
        module.PythonRecipe = type("PythonRecipe", (), {})
        with patch.dict(sys.modules, {
            "pythonforandroid": ModuleType("pythonforandroid"),
            "pythonforandroid.recipe": module,
        }):
            spec = importlib.util.spec_from_file_location(
                "tpk_recipe_test", ROOT / "p4a-recipes/tpk_ar/__init__.py")
            loaded = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(loaded)
        self.recipe = loaded.recipe
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name) / "source"
        self.target = Path(self.temp.name) / "install"
        self.source.mkdir()
        self.recipe.get_build_dir = lambda arch: str(self.source)
        self.recipe.ctx = SimpleNamespace(
            get_python_install_dir=lambda arch: str(self.target))
        self.arch = SimpleNamespace(arch="arm64-v8a")

    def test_stages_python_package_and_license_without_build_artifacts(self):
        package = self.source / "tpk_ar"
        package.mkdir()
        (package / "__init__.py").write_text("version = '0.2.4'\n")
        (package / "blob.py").write_text("# parser\n")
        (package / "__pycache__").mkdir()
        (package / "__pycache__/blob.pyc").write_bytes(b"stale")
        (self.source / "LICENSE").write_text("MIT license fixture\n")
        self.recipe.build_arch(self.arch)
        # A repeat stage must also succeed.
        self.recipe.build_arch(self.arch)
        installed = self.target / "tpk_ar"
        self.assertEqual((installed / "blob.py").read_text(), "# parser\n")
        self.assertEqual((installed / "LICENSE").read_text(), "MIT license fixture\n")
        self.assertFalse((installed / "__pycache__").exists())

    def test_incomplete_source_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "source package or license"):
            self.recipe.build_arch(self.arch)
        self.assertFalse(self.target.exists())

    def test_missing_license_is_rejected(self):
        package = self.source / "tpk_ar"
        package.mkdir()
        (package / "__init__.py").write_text("")
        with self.assertRaisesRegex(RuntimeError, "source package or license"):
            self.recipe.build_arch(self.arch)

    def test_source_version_matches_apk_requirement(self):
        self.assertEqual(self.recipe.name, "tpk_ar")
        self.assertEqual(self.recipe.version, "0.2.4")
        self.assertEqual(len(self.recipe.sha256sum), 64)
        self.assertIn("tpk_ar==" + self.recipe.version,
                      (ROOT / "buildozer.spec").read_text())
        self.assertIn("'tpk_ar'",
                      (ROOT / "p4a-recipes/unitypy/__init__.py").read_text())


if __name__ == "__main__":
    unittest.main()
