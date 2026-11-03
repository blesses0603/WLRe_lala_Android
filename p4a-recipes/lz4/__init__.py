"""Pinned upstream lz4 C extension, compiled for the target Android ABI."""
from pythonforandroid.recipe import CompiledComponentsPythonRecipe


class CodecRecipe(CompiledComponentsPythonRecipe):
    name = 'lz4'
    version = '4.4.5'
    url = 'https://files.pythonhosted.org/packages/57/51/f1b86d93029f418033dddf9b9f79c8d2641e7454080478ee2aab5123173e/lz4-4.4.5.tar.gz'
    sha256sum = '5f0b9e53c1e82e88c10d7c180069363980136b9d7a8306c4dca4f760d60c39f0'
    depends = ['python3', 'setuptools']
    # setup.py loads setuptools_scm, which imports vcs_versioning. These are
    # build tools for p4a's isolated hostpython, not Android runtime modules.
    # CompiledComponentsPythonRecipe installs these before build_ext.
    hostpython_prerequisites = ['setuptools', 'setuptools_scm', 'vcs-versioning']
    call_hostpython_via_targetpython = False


recipe = CodecRecipe()
