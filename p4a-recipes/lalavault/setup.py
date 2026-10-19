"""Stage supplies the original vault implementation as _wlre_vault_native.pyx."""
from setuptools import Extension, setup

setup(
    name="lalavault",
    version="0.0.8",
    ext_modules=[Extension("_wlre_vault_native", ["_wlre_vault_native.pyx"])],
)
