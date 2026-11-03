"""UnityPy 1.25.4 TextAsset reader using upstream's Python fallback.

No host ELF or FMOD libraries are copied. Textures are supplied by the verified
resource database. The upstream optional UnityPyBoost is not required to parse
AssetBundle/TextAsset; GPU/audio export functions are outside this reader.
"""
from pathlib import Path
import shutil
from pythonforandroid.recipe import PythonRecipe
class UnityPyRecipe(PythonRecipe):
    name = 'unitypy'
    version = '1.25.4'
    url = 'https://files.pythonhosted.org/packages/10/a4/5b1c786cae645d30c882eac7933ab7c8916e13f1a571bf7d0f2cdc942a52/unitypy-1.25.4.tar.gz'
    sha256sum = '91d6169d73db8eb5f11fd6531b4e5e980f53dae00d5e3cbab827bbf4765de6d3'
    site_packages_name = 'UnityPy'
    depends = ['python3', 'pillow', 'liblzma', 'lz4', 'brotli', 'attrs', 'fsspec', 'tpk_ar']
    def build_arch(self, arch):
        source = Path(self.get_build_dir(arch.arch)) / 'UnityPy'
        target = Path(self.ctx.get_python_install_dir(arch.arch)) / 'UnityPy'
        if not (source / 'resources/lzma.tpk').is_file():
            raise RuntimeError('UnityPy reviewed type-tree resource missing')
        shutil.copytree(source, target, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('__pycache__','lib','*.so','*.dll','*.dylib'))
recipe = UnityPyRecipe()
