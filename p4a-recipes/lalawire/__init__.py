"""Opt-in python-for-android Cython recipe for LaLa wire.

The stage command supplies src/setup.py and src/_wlre_wire_native.pyx.
This recipe is NOT added to the normal Android Buildozer requirements.
"""
from pythonforandroid.recipe import CythonRecipe, IncludedFilesBehaviour


class LalaWireRecipe(IncludedFilesBehaviour, CythonRecipe):
    name = "lalawire"
    version = "0.0.7"
    src_filename = "src"
    site_packages_name = "_wlre_wire_native"
    depends = ["python3"]


recipe = LalaWireRecipe()
