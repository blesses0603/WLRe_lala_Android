"""Pinned upstream brotli C extension, compiled for the target Android ABI."""
from pythonforandroid.recipe import CppCompiledComponentsPythonRecipe
class CodecRecipe(CppCompiledComponentsPythonRecipe):
    name = 'brotli'
    version = '1.2.1'
    url = 'https://files.pythonhosted.org/packages/cf/81/1546c983678a9b4e77cb4718eaedd1b2caf24a6cdbf1eb8775938d22aff7/brotli-1.2.1.tar.gz'
    sha256sum = '02b2f7b5a83485efe448a44ddf7983def05c3bb1dcf917d4f7154070260e13de'
    depends = ['python3', 'setuptools']
    call_hostpython_via_targetpython = False
recipe = CodecRecipe()
