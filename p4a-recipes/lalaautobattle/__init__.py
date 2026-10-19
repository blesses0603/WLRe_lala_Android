"""Phase05 P0/P1 CythonRecipe for _wlre_auto_battle_native; build only in isolated stage."""
from pythonforandroid.recipe import CythonRecipe, IncludedFilesBehaviour


class NativeCoreRecipe(IncludedFilesBehaviour, CythonRecipe):
    name = "lalaautobattle"
    version = "0.0.8"
    src_filename = "src"
    site_packages_name = "_wlre_auto_battle_native"
    depends = ["python3"]


recipe = NativeCoreRecipe()
