"""P3 per-core SHA-256 incremental ARM64 Cython build cache.

A cache contains ONLY one previously audited native .so and its checksum.
Keys bind exact staged source, recipe, toolchain, Python ABI, runner image and
the verification implementation. A .p3verified marker is never cached.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import importlib.util
from pathlib import Path
import re
import shutil
import struct

from tools.android_build_cache import cache_key

ROOT = Path(__file__).resolve().parents[1]
ARCH = "arm64-v8a"
ABI = ".cpython-314-x86_64-linux-gnu.so"
SCHEMA = 1
CORES = (
    ("lalawire", "_wlre_wire_native"),
    ("lalavault", "_wlre_vault_native"),
    ("lalaruntime", "_wlre_runtime_native"),
    ("lalasessions", "_wlre_sessions_native"),
    ("lalaclient", "_wlre_client_native"),
    ("lalaprotocol", "_wlre_protocol_native"),
    ("lalaautobattle", "_wlre_auto_battle_native"),
    ("lalaexpedition", "_wlre_expedition_native"),
)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(128 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _arm64(path: Path) -> bool:
    if path.is_symlink() or not path.is_file() or not 128 <= path.stat().st_size <= 32 * 1024 * 1024:
        return False
    with path.open("rb") as fd:
        blob = fd.read(64)
    return (len(blob) == 64 and blob[:6] == b"\x7fELF\x02\x01"
            and struct.unpack_from("<H", blob, 16)[0] == 3
            and struct.unpack_from("<H", blob, 18)[0] == 183)


def _recipe_dir(stage: Path, name: str) -> Path:
    return stage / "p4a-recipes" / name


def _filename(module: str) -> str:
    return module + ABI


def _inputs(recipe: Path) -> str:
    """Digest only this recipe's staged source, setup and included headers."""
    if recipe.is_symlink() or not recipe.is_dir():
        raise ValueError("Missing or symlinked native recipe")
    paths = sorted(p for p in recipe.rglob("*")
                   if not set(p.relative_to(recipe).parts) & {"prebuilt", "__pycache__"}
                   and not p.name.startswith(".p3") and p.suffix != ".pyc"
                   and (p.is_file() or p.is_symlink()))
    if not paths:
        raise ValueError("Empty native recipe")
    hashed = hashlib.sha256()
    for path in paths:
        if path.is_symlink() or path.stat().st_size > 3 * 1024 * 1024:
            raise ValueError("Unsafe native recipe input")
        hashed.update(path.relative_to(recipe).as_posix().encode() + b"\x00")
        hashed.update(bytes.fromhex(_sha256(path)))
    return hashed.hexdigest()


def _base_key(spec: Path, *, image_version=None, tool_versions=None,
              helper: Path | None = None, script: Path | None = None) -> str | None:
    image = os.environ.get("ImageVersion") if image_version is None else image_version
    if not image or not re.fullmatch(r"[a-zA-Z0-9_.-]{2,128}", image):
        return None
    helper = helper or ROOT / "p4a-recipes" / "_lala_core_cache.py"
    script = script or Path(__file__)
    if any(not p.is_file() or p.is_symlink() for p in (helper, script)):
        raise ValueError("Missing checked native cache implementation")
    workflow = ROOT / ".github/workflows/android-apk.yml"
    if not workflow.is_file() or workflow.is_symlink():
        raise ValueError("Missing trusted Android build workflow")
    inputs = {
        "workflow_sha256": _sha256(workflow),
        "schema": SCHEMA,
        "runner": "ubuntu-22.04",
        "image_version": image,
        "platform_key": cache_key(spec, tool_versions=tool_versions),
        "python_abi": "3.14",
        "ndk_revision": "r28c",
        "android_api": 35,
        "android_min_api": 31,
        "arch": ARCH,
        "helper_sha256": _sha256(helper),
        "verifier_sha256": _sha256(script),
    }
    body = json.dumps(inputs, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(body).hexdigest()


def compute_keys(stage: Path, *, spec=ROOT / "buildozer.spec",
                 image_version=None, tool_versions=None,
                 helper=None, script=None) -> dict[str, str] | None:
    base = _base_key(Path(spec), image_version=image_version,
                     tool_versions=tool_versions, helper=helper, script=script)
    if base is None:
        return None
    keys = {}
    for name, module in CORES:
        recipe = _recipe_dir(stage, name)
        required = (recipe / "src" / (module + ".pyx"),
                    recipe / "src" / "setup.py", recipe / "__init__.py")
        if any(p.is_symlink() or not p.is_file() for p in required):
            raise ValueError("Missing staged source for " + name)
        raw = "\n".join((base, name, module, _inputs(recipe)))
        keys[name] = hashlib.sha256(raw.encode("ascii")).hexdigest()
    return keys


def write_expected(stage: Path, keys: dict[str, str] | None, output: Path) -> None:
    """Expose only opaque keys to Actions; expected markers are not cached."""
    with output.open("a", encoding="utf-8") as stream:
        stream.write("enabled=" + ("true" if keys is not None else "false") + "\n")
        for name, _ in CORES:
            expected = _recipe_dir(stage, name) / ".p3expected"
            if expected.is_symlink():
                raise ValueError("Unsafe expected-key marker")
            if keys is None:
                expected.unlink(missing_ok=True)
            else:
                expected.write_text(keys[name] + "\n", encoding="ascii")
                stream.write(name + "=" + keys[name] + "\n")


def prepare_recipe_hooks(stage: Path) -> None:
    """Opt in ONLY the disposable eight-recipe staging tree to P3.

    Keep checked-in p4a recipe definitions untouched: this avoids modifying
    host-test fixtures and ensures the normal full build remains available.
    """
    from importlib.util import find_spec

    helper = ROOT / "p4a-recipes" / "_lala_core_cache.py"
    if not helper.is_file() or helper.is_symlink():
        raise ValueError("Missing reviewed P3 Cython recipe helper")
    for name, _ in CORES:
        recipe = _recipe_dir(stage, name)
        definition = recipe / "__init__.py"
        if definition.is_symlink() or not definition.is_file():
            raise ValueError("Missing staged native recipe: " + name)
        source = definition.read_text(encoding="utf-8")
        old_import = "from pythonforandroid.recipe import CythonRecipe, IncludedFilesBehaviour"
        old_base = "(IncludedFilesBehaviour, CythonRecipe)"
        if source.count(old_import) != 1 or source.count(old_base) != 1:
            raise ValueError("Unexpected original native recipe: " + name)
        new_import = (
            "from pythonforandroid.recipe import IncludedFilesBehaviour\n"
            "from pathlib import Path\n"
            "import importlib.util\n"
            "_p3path = Path(__file__).resolve().with_name('_lala_core_cache.py')\n"
            "_p3spec = importlib.util.spec_from_file_location('_lala_p3_' + "
            + repr(name) + ", _p3path)\n"
            "_p3module = importlib.util.module_from_spec(_p3spec)\n"
            "_p3spec.loader.exec_module(_p3module)\n"
            "SHA256CoreRecipe = _p3module.SHA256CoreRecipe"
        )
        new_source = source.replace(old_import, new_import)
        new_source = new_source.replace(old_base,
                                        "(IncludedFilesBehaviour, SHA256CoreRecipe)")
        # Patch and copy to stage only; helper can never enter the APK source.
        definition.write_text(new_source, encoding="utf-8")
        shutil.copyfile(helper, recipe / "_lala_core_cache.py")


def _record(module: str, key: str, source: Path, binary: Path) -> dict:
    return {
        "schema": SCHEMA, "key": key, "module": module,
        "filename": _filename(module),
        "source_sha256": _sha256(source),
        "binary_sha256": _sha256(binary),
    }


def _clear(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def verify_restored(stage: Path, keys: dict[str, str] | None) -> dict[str, bool]:
    """Reject incorrect source, ABI, SHA or unexpected cached files."""
    results = {}
    for name, module in CORES:
        recipe = _recipe_dir(stage, name)
        cache = recipe / "prebuilt"
        mark = recipe / ".p3verified"
        if mark.is_symlink():
            raise ValueError("Unsafe P3 verified marker")
        mark.unlink(missing_ok=True)
        accepted = False
        if keys and cache.is_dir() and not cache.is_symlink():
            binary = cache / _filename(module)
            manifest = cache / "manifest.json"
            try:
                if (set(p.name for p in cache.iterdir()) ==
                        {"manifest.json", _filename(module)}
                        and manifest.is_file() and not manifest.is_symlink()
                        and manifest.stat().st_size <= 4096 and _arm64(binary)):
                    record = json.loads(manifest.read_text(encoding="utf-8"))
                    expected = _record(
                        module, keys[name], recipe / "src" / (module + ".pyx"), binary)
                    accepted = record == expected
            except (OSError, ValueError, TypeError, UnicodeError):
                accepted = False
        if accepted:
            mark.write_text(keys[name] + "\n", encoding="ascii")
            print("LALA_P3_ACCEPT " + name, flush=True)
        else:
            _clear(cache)
            print("LALA_P3_REBUILD " + name, flush=True)
        results[name] = accepted
    return results


def export_audited(stage: Path, keys: dict[str, str]) -> None:
    """Export only after a fully signed APK has passed the native gate."""
    install = (stage / ".buildozer/android/platform/build-arm64-v8a"
               / "build/python-installs/wlrelala/arm64-v8a")
    if not install.is_dir() or install.is_symlink():
        raise ValueError("Missing p4a installed ARM64 site-packages")
    artifacts = {}
    for name, module in CORES:
        binary = install / _filename(module)
        if not _arm64(binary):
            raise ValueError("Missing or invalid compiled ARM64 core: " + name)
        src = _recipe_dir(stage, name) / "src" / (module + ".pyx")
        if src.is_symlink() or not src.is_file():
            raise ValueError("Staged Cython source changed: " + name)
        artifacts[name] = (binary, _record(module, keys[name], src, binary))
    for name, module in CORES:
        binary, record = artifacts[name]
        recipe = _recipe_dir(stage, name)
        expected = recipe / ".p3expected"
        if expected.is_symlink() or expected.read_text(encoding="ascii").strip() != keys[name]:
            raise ValueError("Staged source hash changed before publication")
        cache = recipe / "prebuilt"
        _clear(cache)
        cache.mkdir(parents=True)
        shutil.copyfile(binary, cache / record["filename"])
        (cache / "manifest.json").write_text(
            json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8")
        (recipe / ".p3verified").unlink(missing_ok=True)
        print("LALA_P3_EXPORT " + name, flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare", "keys", "verify", "export"))
    parser.add_argument("--stage", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if args.command == "prepare":
        prepare_recipe_hooks(args.stage)
        return
    keys = compute_keys(args.stage)
    if args.command == "keys":
        output = args.output or Path(os.environ.get("GITHUB_OUTPUT", ""))
        if str(output) == ".":
            raise ValueError("GitHub output file required")
        write_expected(args.stage, keys, output)
    elif args.command == "verify":
        verify_restored(args.stage, keys)
    else:
        if keys is None:
            raise ValueError("Runner image unknown; P3 export disabled")
        export_audited(args.stage, keys)


if __name__ == "__main__":
    main()
