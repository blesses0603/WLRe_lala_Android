"""P3: eight independent SHA-256-keyed native Cython build artifacts.

Only the trusted, explicitly dispatched main/tag APK job may restore/save
these non-secret ARM64 extensions. Each binary is checked again by its p4a
recipe and every newly assembled APK still runs the full release gate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil

from tools.android_build_cache import ROOT, cache_key
from tools.android_native_cores import CORE_LIST
from tools.android_native_wire import _arm64_elf

SCHEMA = 1
MAX_SO = 64 * 1024 * 1024
CORES = (
    ("lalawire", "_wlre_wire_native"),
    ("lalavault", "_wlre_vault_native"),
) + tuple((recipe, native) for _, recipe, native, _ in CORE_LIST)
CACHE_REL = Path(".buildozer/android/lala-core-cache")
PLAN_REL = Path(".buildozer/android/lala-core-plan.json")
INSTALL_REL = Path(".buildozer/android/platform/build-arm64-v8a/build/python-installs")


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _json_digest(value: dict) -> str:
    return _digest(json.dumps(value, sort_keys=True, separators=(",", ":"),
                              ensure_ascii=True).encode("ascii"))


def _regular(path: Path, maximum: int) -> bytes:
    if not path.is_file() or path.is_symlink():
        raise ValueError("Missing or symlinked P3 input")
    if path.stat().st_size > maximum:
        raise ValueError("Oversized P3 input")
    return path.read_bytes()


def keys(stage: Path, *, image_version: str | None = None,
         tool_versions: dict | None = None, spec: Path = ROOT / "buildozer.spec") -> dict:
    """Hash per-core staged Python implementation and recipe, not app Patch."""
    image = os.environ.get("ImageVersion") if image_version is None else image_version
    if not image or not re.fullmatch(r"[A-Za-z0-9_.-]{2,128}", image):
        return {}
    platform = cache_key(spec, tool_versions=tool_versions)
    shared = _digest(_regular(stage / "p4a-recipes/lala_core_incremental.py", 64 * 1024))
    # The receipt producer is also a relevant part of the build contract.
    generator = _digest(_regular(Path(__file__), 128 * 1024))
    found = {}
    for name, extension in CORES:
        folder = stage / "p4a-recipes" / name
        inputs = {
            filename: _digest(_regular(folder / filename, 2 * 1024 * 1024))
            for filename in ("__init__.py", "src/setup.py", "src/" + extension + ".pyx")
        }
        found[name] = _json_digest({
            "schema": SCHEMA, "runner_image": image, "platform": platform,
            "python_target": "3.14", "arch": "arm64-v8a",
            "ndk": "r28c", "shared_helper": shared, "receipt_generator": generator,
            "recipe": name, "native_module": extension, "sources": inputs,
        })
    if len(found) != 8:
        raise ValueError("P3 requires exactly eight independent cores")
    return found


def cache_folder(stage: Path, recipe: str) -> Path:
    if recipe not in dict(CORES):
        raise ValueError("Unknown LaLa native recipe")
    return stage / CACHE_REL / recipe


def _receipt(stage: Path, recipe: str, key: str) -> Path | None:
    folder = cache_folder(stage, recipe)
    if folder.is_symlink() or not folder.is_dir():
        return None
    receipt = folder / "receipt.json"
    try:
        info = json.loads(_regular(receipt, 4096))
        if info.get("schema") != SCHEMA or info.get("key") != key:
            return None
        filename = info.get("filename", "")
        extension = dict(CORES)[recipe]
        if not re.fullmatch(re.escape(extension) + r"(?:\.[A-Za-z0-9_+.-]+)?\.so",
                            filename):
            return None
        so = folder / filename
        data = _regular(so, MAX_SO)
        if (len(data) < 64 or len(data) != info.get("size")
                or _digest(data) != info.get("sha256")
                or not _arm64_elf(data)):
            return None
        return so
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return None


def plan(stage: Path, *, image_version: str | None = None,
         tool_versions: dict | None = None) -> dict:
    stage = stage.resolve(strict=True)
    result = keys(stage, image_version=image_version, tool_versions=tool_versions)
    if not result:
        return {"enabled": False, "keys": {}}
    return {"enabled": True, "keys": result}


def prepare(stage: Path, **kwargs) -> dict:
    """Validate restored artifacts before p4a, remove invalid snapshots."""
    info = plan(stage, **kwargs)
    target = stage / PLAN_REL
    target.parent.mkdir(parents=True, exist_ok=True)
    # No signing material, local account data or absolute paths in the plan.
    target.write_text(json.dumps({"schema": SCHEMA, "keys": info["keys"]},
                                 sort_keys=True), encoding="utf-8")
    hits = []
    misses = []
    for name, key in info["keys"].items():
        if _receipt(stage, name, key):
            hits.append(name)
        else:
            folder = cache_folder(stage, name)
            if folder.is_symlink():
                folder.unlink()
            elif folder.exists():
                shutil.rmtree(folder)
            misses.append(name)
    print("P3 cache: " + str(len(hits)) + " HIT, " + str(len(misses)) +
          " MISS; hits=" + ",".join(hits) + "; misses=" + ",".join(misses))
    return {"hits": hits, "misses": misses, "keys": info["keys"]}


def save(stage: Path, **kwargs) -> dict:
    """After signed APK gate, snapshot the eight unique installed ARM64 .so."""
    info = plan(stage, **kwargs)
    if not info["enabled"]:
        print("P3 disabled: missing trusted runner image")
        return {"saved": []}
    install = stage / INSTALL_REL
    if not install.is_dir() or install.is_symlink():
        raise ValueError("P3 target python-installs directory missing")
    saved = []
    for name, extension in CORES:
        key = info["keys"][name]
        if _receipt(stage, name, key):
            continue
        expression = re.compile(re.escape(extension) + r"(?:\.[A-Za-z0-9_+.-]+)?\.so")
        candidates = [
            p for p in install.rglob("*.so")
            if p.parent.name == "arm64-v8a" and expression.fullmatch(p.name)
        ]
        if len(candidates) != 1:
            raise ValueError("P3 requires exactly one installed extension for " + name)
        data = _regular(candidates[0], MAX_SO)
        if len(data) < 64 or not _arm64_elf(data):
            raise ValueError("P3 invalid AArch64 ELF for " + name)
        folder = cache_folder(stage, name)
        if folder.is_symlink():
            raise ValueError("P3 cache folder is a symlink")
        if folder.exists():
            shutil.rmtree(folder)
        folder.mkdir(parents=True)
        binary = folder / candidates[0].name
        binary.write_bytes(data)
        receipt = {
            "schema": SCHEMA, "key": key, "filename": binary.name,
            "size": len(data), "sha256": _digest(data),
        }
        (folder / "receipt.json").write_text(
            json.dumps(receipt, sort_keys=True) + "\n", encoding="utf-8")
        if not _receipt(stage, name, key):
            raise RuntimeError("P3 snapshot failed post-write verification")
        saved.append(name)
    print("P3 valid native core snapshots: " + str(len(info["keys"])) +
          "/8; newly saved=" + ",".join(saved))
    return {"saved": saved}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("plan", "prepare", "save"))
    parser.add_argument("--stage", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.action == "plan":
        info = plan(args.stage)
        output = os.environ.get("GITHUB_OUTPUT")
        if not output:
            raise RuntimeError("GITHUB_OUTPUT is required for P3 plan")
        with open(output, "a", encoding="utf-8") as stream:
            stream.write("enabled=" + ("true" if info["enabled"] else "false") + "\n")
            for name, value in info["keys"].items():
                stream.write(name + "=" + value + "\n")
        print("P3 independent core SHA-256 keys: " + str(len(info["keys"])))
    elif args.action == "prepare":
        prepare(args.stage)
    else:
        save(args.stage)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
