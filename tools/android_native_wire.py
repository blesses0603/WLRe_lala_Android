"""Opt-in ARM64 Cython staging and fail-closed APK inspection.

This does NOT produce a native binary by itself. Run Buildozer in the staged
source tree using the local python-for-android recipe after unit tests pass.
"""
from __future__ import annotations

import argparse
import configparser
import io
from pathlib import Path
import re
import shutil
import struct
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
WIRE_REL = Path("wlre/network/wire.py")
RECIPE_ROOT = Path("p4a-recipes/lalawire")
NATIVE_BASENAME = "_wlre_wire_native"
EXCLUDE_ROOTS = frozenset({
    ".git", ".github", ".buildozer", ".gradle", ".kivy", ".venv", "venv",
    "bin", "android-output", "phone-output", "tests", "tools", "docs",
    "dist_nuitka", "p4a-recipes", "__pycache__", ".pytest_cache",
})
SHIM = '''"""Android-native wire API. Implementation lives in an ARM64 Cython extension."""\nfrom _wlre_wire_native import ProtocolError, Reader, Writer, Packet, encode, FrameDecoder\n\n__all__ = ["ProtocolError", "Reader", "Writer", "Packet", "encode", "FrameDecoder"]\n'''


def _under(child: Path, parent: Path) -> bool:
    return child == parent or parent in child.parents


def _assert_clean_source(root: Path) -> None:
    if not (root / "buildozer.spec").is_file() or not (root / WIRE_REL).is_file():
        raise ValueError("Expected project buildozer.spec and wlre/network/wire.py")
    if not (root / RECIPE_ROOT / "__init__.py").is_file():
        raise ValueError("Native recipe is missing")
    if not (root / RECIPE_ROOT / "setup.py").is_file():
        raise ValueError("Native recipe setup.py is missing")


def _copy_source(source: Path, destination: Path) -> None:
    def ignore(directory, names):
        ignored = []
        for name in names:
            path = Path(directory) / name
            if name in EXCLUDE_ROOTS or name.startswith(".") or path.is_symlink():
                ignored.append(name)
        return ignored
    shutil.copytree(source, destination, ignore=ignore, symlinks=False)


def stage(root: Path, output: Path) -> Path:
    """Create disposable Buildozer input; do not mutate current app sources."""
    root = root.resolve(strict=True)
    _assert_clean_source(root)
    output = output.resolve()
    if _under(output, root) or _under(root, output):
        raise ValueError("Native stage must be outside the repository tree")
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite native stage {output}")
    for path in (root / WIRE_REL, root / "buildozer.spec", root / RECIPE_ROOT / "__init__.py"):
        if path.is_symlink():
            raise ValueError(f"Source contains forbidden symlink: {path}")
    try:
        _copy_source(root, output)
        wire = output / WIRE_REL
        native_source = output / RECIPE_ROOT / "src" / f"{NATIVE_BASENAME}.pyx"
        native_source.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(wire, native_source)
        wire.write_text(SHIM, encoding="utf-8")
        # Original wire implementation never enters the application source tree.
        if not native_source.read_bytes().startswith(b'"""Strict packet primitives'):
            raise ValueError("Unexpected wire implementation baseline")
        shutil.copy2(root / RECIPE_ROOT / "__init__.py", output / RECIPE_ROOT / "__init__.py")
        shutil.copy2(root / RECIPE_ROOT / "setup.py", output / RECIPE_ROOT / "src" / "setup.py")
        spec = output / "buildozer.spec"
        config = configparser.ConfigParser(interpolation=None)
        if not config.read(spec, encoding="utf-8"):
            raise ValueError("Staged Buildozer spec could not be read")
        app = config["app"]
        if app.get("android.minapi", "").strip() != "31" or app.get("android.archs", "").strip() != "arm64-v8a":
            raise ValueError("Native pilot requires Android 12+/ARM64-only")
        requirements = [p.strip() for p in app["requirements"].split(",") if p.strip()]
        if "lalawire" in requirements:
            raise ValueError("Buildozer source already declares native wire")
        text = spec.read_text(encoding="utf-8")
        text = re.sub(r"(?m)^(requirements\s*=\s*)([^\n]+)$",
                      lambda m: m[1] + m[2] + ",lalawire", text, count=1)
        text = text.replace("source.exclude_dirs = ", "source.exclude_dirs = p4a-recipes,", 1)
        if "p4a.local_recipes" in text:
            raise ValueError("Unexpected pre-existing p4a.local_recipes setting")
        text = text.replace("p4a.branch = ",
                            "p4a.local_recipes = p4a-recipes\np4a.branch = ", 1)
        enabled = re.search(r"(?m)^requirements = (.+)$", text)
        if ("p4a.local_recipes = p4a-recipes" not in text
                or enabled is None
                or "lalawire" not in [p.strip() for p in enabled[1].split(",")]):
            raise ValueError("Could not enable local recipe")
        spec.write_text(text, encoding="utf-8")
        return output
    except Exception:
        shutil.rmtree(output, ignore_errors=True)
        raise


def _candidate(member: str) -> bool:
    name = member.rsplit("/", 1)[-1]
    return bool(re.fullmatch(r"_wlre_wire_native(?:\.[A-Za-z0-9_+.-]+)?\.so", name))


def _arm64_elf(blob: bytes) -> bool:
    return (len(blob) >= 20 and blob[:4] == b"\x7fELF" and blob[4] == 2
            and blob[5] == 1 and struct.unpack_from("<H", blob, 18)[0] == 183)


def verify_apk(path: Path) -> dict:
    """Validate the actual native payload. Never accept a host Linux .so."""
    found, suspicious = [], []
    with zipfile.ZipFile(path) as apk:
        members = apk.namelist()
        if not any(name.startswith("lib/arm64-v8a/") for name in members):
            raise ValueError("APK does not contain Android ARM64 libraries")
        for name in members:
            if _candidate(name):
                if not _arm64_elf(apk.read(name)):
                    raise ValueError(f"Non-ARM64 native wire binary: {name}")
                found.append(name)
            if name.endswith(("_wlre_wire_native.py", "_wlre_wire_native.pyc", "_wlre_wire_native.pyx")):
                suspicious.append(name)
        if "assets/private.tar" not in members:
            raise ValueError("Missing expected private.tar")
        with tarfile.open(fileobj=io.BytesIO(apk.read("assets/private.tar")), mode="r:*") as bundle:
            for info in bundle:
                name = info.name.replace("\\", "/")
                if info.issym() or info.islnk():
                    raise ValueError("Link entry in APK private.tar")
                if any(segment == ".." for segment in name.split("/")):
                    raise ValueError("Traversal in APK private.tar")
                if not info.isfile():
                    continue
                if _candidate(name):
                    blob = bundle.extractfile(info).read()
                    if not _arm64_elf(blob):
                        raise ValueError(f"Non-ARM64 native wire binary: {name}")
                    found.append(name)
                if name.endswith(("_wlre_wire_native.py", "_wlre_wire_native.pyc",
                                  "_wlre_wire_native.pyx", "wlre/network/wire.py")):
                    suspicious.append(name)
                if name.endswith("wlre/network/wire.pyc"):
                    body = bundle.extractfile(info).read()
                    if b"Strict packet primitives and the server codec" in body:
                        suspicious.append(name + " (original implementation bytecode)")
        if suspicious:
            raise ValueError("Native wire bundle leaks implementation: " + ", ".join(suspicious))
        if not found:
            raise ValueError("Missing Android ARM64 native wire extension")
    return {"arm64_wire_extensions": found, "source_leaks": 0}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="operation", required=True)
    staging = sub.add_parser("stage")
    staging.add_argument("--source", type=Path, default=ROOT)
    staging.add_argument("--output", type=Path, required=True)
    audit = sub.add_parser("verify-apk")
    audit.add_argument("apk", type=Path)
    opts = parser.parse_args(argv)
    if opts.operation == "stage":
        print(stage(opts.source, opts.output))
    else:
        print(verify_apk(opts.apk))


if __name__ == "__main__":
    main()
