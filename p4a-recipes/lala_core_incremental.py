"""P3: restore only independently verified ARM64 LaLa Cython extensions.

This runs inside a disposable p4a recipe.  A cache miss ALWAYS uses the
original CythonRecipe.build_arch; caching never bypasses APK release audits.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil

from pythonforandroid.recipe import Recipe

SCHEMA = 1
MAX_SO = 64 * 1024 * 1024


def reuse(recipe, arch):
    root = os.environ.get("LALA_P3_CORE_CACHE")
    plan_path = os.environ.get("LALA_P3_CORE_PLAN")
    if not root or not plan_path or arch.arch != "arm64-v8a":
        return False
    name = recipe.name
    extension = recipe.site_packages_name
    if not re.fullmatch(r"lala[a-z]+", name) or not extension.startswith("_wlre_"):
        return False
    try:
        plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
        if plan.get("schema") != SCHEMA or name not in plan.get("keys", {}):
            return False
        folder = Path(root) / name
        if folder.is_symlink():
            return False
        meta_path = folder / "receipt.json"
        if meta_path.is_symlink() or not meta_path.is_file():
            return False
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if meta.get("schema") != SCHEMA or meta.get("key") != plan["keys"][name]:
            return False
        filename = meta.get("filename", "")
        if not re.fullmatch(re.escape(extension) + r"(?:\.[A-Za-z0-9_+.-]+)?\.so", filename):
            return False
        source = folder / filename
        if source.is_symlink() or not source.is_file():
            return False
        size = source.stat().st_size
        if not 64 <= size <= MAX_SO or size != meta.get("size"):
            return False
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        if digest != meta.get("sha256"):
            return False
        with source.open("rb") as stream:
            header = stream.read(64)
        # ELF64, little-endian, ET_DYN, AArch64, version 1, correct header size.
        if not (header[:7] == b"\x7fELF\x02\x01\x01"
                and int.from_bytes(header[16:18], "little") == 3
                and int.from_bytes(header[18:20], "little") == 183
                and int.from_bytes(header[20:24], "little") == 1
                and int.from_bytes(header[52:54], "little") == 64):
            return False
        Recipe.build_arch(recipe, arch)
        dest = Path(recipe.ctx.get_python_install_dir(arch.arch))
        dest.mkdir(parents=True, exist_ok=True)
        destination = dest / filename
        if destination.is_symlink() or destination.exists():
            raise RuntimeError("P3 cache destination is unexpectedly occupied: " + name)
        shutil.copyfile(source, destination)
        if hashlib.sha256(destination.read_bytes()).hexdigest() != digest:
            destination.unlink(missing_ok=True)
            raise RuntimeError("P3 cached native extension failed post-copy verification")
        print("P3 verified SHA-256 native core reuse: " + name, flush=True)
        return True
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        # Stale or malformed cache must never make a valid clean build fail.
        return False
