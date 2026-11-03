"""Install the pinned pure-Python TPK parser from its source-only release."""
from pathlib import Path
import shutil

from pythonforandroid.recipe import PythonRecipe


class TpkArRecipe(PythonRecipe):
    name = 'tpk_ar'
    version = '0.2.4'
    url = 'https://files.pythonhosted.org/packages/fa/02/654a73cbd323970b5c1551881968dbadec1d697984fff5fdd33b66764dfc/tpk_ar-0.2.4.tar.gz'
    sha256sum = 'd64897e5a0bcddd58e8a7d4dd922f372da984a0f98bc3b460ec869aab906ee78'
    site_packages_name = 'tpk_ar'
    depends = ['python3']

    def build_arch(self, arch):
        # PyPI 0.2.4 provides only an sdist; p4a's binary-only fallback cannot
        # install it. Like the UnityPy recipe, copy the reviewed Python package
        # directly, without invoking a host compiler or downloading a wheel.
        source = Path(self.get_build_dir(arch.arch))
        package = source / 'tpk_ar'
        license_file = source / 'LICENSE'
        if not (package / '__init__.py').is_file() or not license_file.is_file():
            raise RuntimeError('TPK parser source package or license missing')
        target = Path(self.ctx.get_python_install_dir(arch.arch)) / 'tpk_ar'
        shutil.copytree(
            package, target, dirs_exist_ok=True,
            ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        shutil.copy2(license_file, target / 'LICENSE')


recipe = TpkArRecipe()
