"""Opt-in python-for-android Cython recipe for LaLa wire.

The stage command supplies src/setup.py and src/_wlre_wire_native.pyx.
This recipe is NOT added to the normal Android Buildozer requirements.
"""
from pythonforandroid.recipe import CythonRecipe, IncludedFilesBehaviour
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

_p3_spec = spec_from_file_location(
    "lala_p3_core_cache", Path(__file__).resolve().parents[1] / "lala_core_incremental.py"
)
_p3_cache = module_from_spec(_p3_spec)
_p3_spec.loader.exec_module(_p3_cache)


class LalaWireRecipe(IncludedFilesBehaviour, CythonRecipe):
    name = "lalawire"
    version = "0.0.7"
    src_filename = "src"
    site_packages_name = "_wlre_wire_native"
    depends = ["python3"]

    def build_arch(self, arch):
        # An absent, stale or damaged cache always follows p4a's original
        # Cython compilation and install path. Never skip APK security gates.
        if not _p3_cache.reuse(self, arch):
            super().build_arch(arch)


recipe = LalaWireRecipe()
