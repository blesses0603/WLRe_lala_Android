"""Build inputs are materialized under recipe src/ for p4a CythonRecipe."""
from setuptools import Extension, setup

setup(
    name="lalawire",
    version="0.0.7",
    ext_modules=[Extension("_wlre_wire_native", ["_wlre_wire_native.pyx"])],
)
