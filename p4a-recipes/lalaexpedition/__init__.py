"""Phase05 P0/P1 CythonRecipe for _wlre_expedition_native; build only in isolated stage."""
from pythonforandroid.recipe import CythonRecipe, IncludedFilesBehaviour


class NativeCoreRecipe(IncludedFilesBehaviour, CythonRecipe):
    name = "lalaexpedition"
    version = "0.0.8"
    src_filename = "src"
    site_packages_name = "_wlre_expedition_native"
    depends = ["python3"]


recipe = NativeCoreRecipe()
