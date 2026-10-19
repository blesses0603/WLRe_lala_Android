"""Source is staged from the canonical Python core, never shipped as .pyx."""
from setuptools import Extension, setup

setup(
    name="lalaautobattle",
    version="0.0.8",
    ext_modules=[Extension("_wlre_auto_battle_native", ["_wlre_auto_battle_native.pyx"])],
)
