"""Phase05 P0/P1 CythonRecipe for _wlre_runtime_native; build only in isolated stage."""
from pythonforandroid.recipe import CythonRecipe, IncludedFilesBehaviour


class NativeCoreRecipe(IncludedFilesBehaviour, CythonRecipe):
    name = "lalaruntime"
    version = "0.0.8"
    src_filename = "src"
    site_packages_name = "_wlre_runtime_native"
    depends = ["python3"]


recipe = NativeCoreRecipe()
