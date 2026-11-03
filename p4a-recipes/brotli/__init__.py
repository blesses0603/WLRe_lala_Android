"""Pinned Brotli Android recipe: upstream 1.2.1 uses bin/ as build base."""
import glob

import sh
from pythonforandroid.logger import info, shprint
from pythonforandroid.recipe import CppCompiledComponentsPythonRecipe
from pythonforandroid.util import current_directory


class CodecRecipe(CppCompiledComponentsPythonRecipe):
    name = 'brotli'
    version = '1.2.1'
    url = 'https://files.pythonhosted.org/packages/cf/81/1546c983678a9b4e77cb4718eaedd1b2caf24a6cdbf1eb8775938d22aff7/brotli-1.2.1.tar.gz'
    sha256sum = '02b2f7b5a83485efe448a44ddf7983def05c3bb1dcf917d4f7154070260e13de'
    depends = ['python3', 'setuptools']
    call_hostpython_via_targetpython = False

    def build_compiled_components(self, arch):
        # Brotli 1.2.1's setup.py writes extension artifacts to bin/lib.*,
        # whereas p4a's generic recipe only searches build/lib.*.
        info('Building compiled components in {}'.format(self.name))
        env = self.get_recipe_env(arch)
        hostpython = sh.Command(self.hostpython_location)
        with current_directory(self.get_build_dir(arch.arch)):
            if self.install_in_hostpython:
                shprint(hostpython, 'setup.py', 'clean', '--all', _env=env)
            shprint(hostpython, 'setup.py', self.build_cmd, '-v',
                    _env=env, *self.setup_extra_args)
            candidates = sorted(set(glob.glob('build/lib.*') + glob.glob('bin/lib.*')))
            if not candidates:
                raise RuntimeError('Brotli build produced no build/lib.* or bin/lib.* output')
            for build_dir in candidates:
                shprint(sh.find, build_dir, '-name', '"*.o"', '-exec',
                        env['STRIP'], '{}', ';', _env=env)


recipe = CodecRecipe()
