"""Isolated Phase05 Cython recipe; no signing credentials enter this recipe."""
from pythonforandroid.recipe import CythonRecipe, IncludedFilesBehaviour
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

_p3_spec = spec_from_file_location(
    "lala_p3_core_cache", Path(__file__).resolve().parents[1] / "lala_core_incremental.py"
)
_p3_cache = module_from_spec(_p3_spec)
_p3_spec.loader.exec_module(_p3_cache)


class LalaVaultRecipe(IncludedFilesBehaviour, CythonRecipe):
    name = "lalavault"
    version = "0.0.8"
    src_filename = "src"
    site_packages_name = "_wlre_vault_native"
    depends = ["python3"]

    def build_arch(self, arch):
        # An absent, stale or damaged cache always follows p4a's original
        # Cython compilation and install path. Never skip APK security gates.
        if not _p3_cache.reuse(self, arch):
            super().build_arch(arch)


recipe = LalaVaultRecipe()
