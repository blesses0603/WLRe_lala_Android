"""Source is staged from the canonical Python core, never shipped as .pyx."""
from setuptools import Extension, setup

setup(
    name="lalaruntime",
    version="0.0.8",
    ext_modules=[Extension("_wlre_runtime_native", ["_wlre_runtime_native.pyx"])],
)
