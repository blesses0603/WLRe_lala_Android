"""Isolated Phase05 Cython recipe; no signing credentials enter this recipe."""
from pythonforandroid.recipe import CythonRecipe, IncludedFilesBehaviour


class LalaVaultRecipe(IncludedFilesBehaviour, CythonRecipe):
    name = "lalavault"
    version = "0.0.8"
    src_filename = "src"
    site_packages_name = "_wlre_vault_native"
    depends = ["python3"]


recipe = LalaVaultRecipe()
