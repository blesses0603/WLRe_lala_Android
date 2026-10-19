"""Phase05 full P0/P1 staged Cython coverage without modifying app checkout.

Experimental APK build is MANUAL ONLY after all eight cores are staged.
Phase04 wire and Phase05 vault audits are prerequisite checks.
"""
from __future__ import annotations

import argparse
import ast
import importlib.util
import io
import marshal
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import types
import zipfile

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.android_native_wire import _arm64_elf, _host_only_so_name
from tools.android_native_vault import (
    stage as stage_vault, verify_apk as verify_vault_apk,
)

ROOT = Path(__file__).resolve().parents[1]

# The Phase04 wire and Phase05 vault are already implemented by independent
# recipes. Only the six outstanding P0/P1 implementations are listed here.
CORE_LIST = (
    ("android_app/runtime.py", "lalaruntime", "_wlre_runtime_native", "P0"),
    ("android_app/sessions.py", "lalasessions", "_wlre_sessions_native", "P0"),
    ("wlre/network/client.py", "lalaclient", "_wlre_client_native", "P0"),
    ("wlre/network/protocol.py", "lalaprotocol", "_wlre_protocol_native", "P0"),
    ("wlre/services/battle/auto_battle.py", "lalaautobattle", "_wlre_auto_battle_native", "P1"),
    ("wlre/services/expedition.py", "lalaexpedition", "_wlre_expedition_native", "P1"),
)


def shim(native: str) -> str:
    # Keep public and private exported attributes available to callers,
    # including protocol constants, dataclasses and legacy helper names.
    # Module-global assignments inside native implementations still target
    # the native module: monkeypatch equivalence needs separate host checks.
    return (
        '"""Phase05 ARM64-native core compatibility import; no implementation."""\n'
        f"import {native} as _native\n"
        "__all__ = tuple(n for n in vars(_native) if not (n.startswith('__') and n.endswith('__')))\n"
        "globals().update({n: getattr(_native, n) for n in __all__})\n"
        "def __getattr__(name):\n"
        "    return getattr(_native, name)\n"
    )


def _source_check(source: Path) -> None:
    paths = [Path(rel) for rel, _, _, _ in CORE_LIST]
    if len(paths) != len(set(paths)):
        raise ValueError("Duplicate sensitive core source path")
    for rel, recipe, _, _ in CORE_LIST:
        module = source / rel
        folder = source / "p4a-recipes" / recipe
        for candidate in (module, folder / "__init__.py", folder / "setup.py"):
            if not candidate.is_file() or candidate.is_symlink():
                raise ValueError("Missing or symlinked Phase05 core source/recipe: " + str(candidate))
        try:
            ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
        except (UnicodeDecodeError, SyntaxError) as exc:
            raise ValueError("Unparseable Phase05 source " + rel) from exc


def stage(source: Path, output: Path) -> Path:
    """Stage native wire, vault, AND remaining P0/P1 cores atomically."""
    source = source.resolve(strict=True)
    _source_check(source)
    # stage_vault refuses in-repo destinations, symlinks and overwrites.
    stage_vault(source, output)
    output = output.resolve()
    try:
        for rel, recipe, extension, _ in CORE_LIST:
            target = output / rel
            native_root = output / "p4a-recipes" / recipe
            native_src = native_root / "src"
            native_src.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, native_src / (extension + ".pyx"))
            target.write_text(shim(extension), encoding="utf-8")
            # Source copying excluded p4a-recipes; restore only build inputs.
            shutil.copy2(source / "p4a-recipes" / recipe / "__init__.py",
                         native_root / "__init__.py")
            shutil.copy2(source / "p4a-recipes" / recipe / "setup.py",
                         native_src / "setup.py")
        spec = output / "buildozer.spec"
        text = spec.read_text(encoding="utf-8")
        matches = list(re.finditer(r"(?m)^requirements\s*=\s*([^\n]+)$", text))
        if len(matches) != 1:
            raise ValueError("Expected exactly one requirements line in staged spec")
        dependencies = [x.strip() for x in matches[0].group(1).split(",")]
        if not {"lalawire", "lalavault"}.issubset(dependencies):
            raise ValueError("Native wire/vault prerequisites missing")
        appended = [recipe for _, recipe, _, _ in CORE_LIST]
        if set(appended).intersection(dependencies):
            raise ValueError("Duplicate Phase05 recipes in staged spec")
        text = text[:matches[0].end(1)] + "," + ",".join(appended) + text[matches[0].end(1):]
        spec.write_text(text, encoding="utf-8")
        return output
    except Exception:
        shutil.rmtree(output, ignore_errors=True)
        raise


def _is_core_pyc(name: str, rel: str) -> bool:
    normalized = name.replace("\\", "/")
    p = Path(rel)
    return re.search(
        r"(?:^|/)" + re.escape(p.parent.as_posix()) +
        r"/(?:__pycache__/)?"+ re.escape(p.stem) +
        r"(?:\.cpython-\d+[a-z]*)?\.pyc$",
        normalized,
    ) is not None


def _exact_shim(blob: bytes, extension: str, *, pyc_python: Path | None = None) -> bool:
    if pyc_python is not None and pyc_python.resolve() != Path(sys.executable).resolve():
        try:
            check = subprocess.run(
                [str(pyc_python), "-I", str(Path(__file__).resolve()), "_verify-core-pyc", extension],
                input=blob, capture_output=True, timeout=15, check=False,
            )
            return check.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            return False
    if len(blob) < 16 or len(blob) > 1048576 or blob[:4] != importlib.util.MAGIC_NUMBER:
        return False
    try:
        stream = io.BytesIO(blob[16:])
        code = marshal.load(stream)
    except (ValueError, EOFError, TypeError):
        return False
    if stream.tell() != len(blob) - 16 or not isinstance(code, types.CodeType):
        return False

    def signature(compiled):
        return (compiled.co_code, compiled.co_names, compiled.co_consts,
                compiled.co_varnames, compiled.co_cellvars, compiled.co_freevars)
    return any(signature(code) == signature(compile(shim(extension), "<native-core-shim>", "exec", optimize=opt))
               for opt in (0, 1, 2))


def verify_apk(apk: Path, *, pyc_python: Path | None = None) -> dict:
    """Ensure the existing wire+vault and all 6 remaining cores are native."""
    verify_vault_apk(apk, pyc_python=pyc_python)
    native_count = {rel: 0 for rel, _, _, _ in CORE_LIST}
    shim_count = {rel: 0 for rel, _, _, _ in CORE_LIST}
    leaked = []
    native_names = {extension: rel for rel, _, extension, _ in CORE_LIST}

    def inspect(name: str, data: bytes, archive: str):
        normalized = name.replace("\\", "/")
        basename = normalized.rsplit("/", 1)[-1]
        location = archive + ":" + normalized
        for extension, rel in native_names.items():
            if re.fullmatch(re.escape(extension) + r"(?:\.[A-Za-z0-9_+.-]+)?\.so", basename):
                if _host_only_so_name(normalized) or not _arm64_elf(data):
                    raise ValueError("Non-ARM64 Phase05 core: " + location)
                if (archive == "lib/arm64-v8a/libpybundle.so" and
                        re.search(r"(?:^|/)site-packages/" + re.escape(extension) +
                                  r"(?:\.[A-Za-z0-9_+.-]+)?\.so$", normalized)):
                    native_count[rel] += 1
                else:
                    leaked.append(location + " (duplicate/non-importable native)")
            if (basename in {extension + ".py", extension + ".pyx", extension + ".pyc"}
                    or normalized.endswith(rel)):
                leaked.append(location + " (source implementation)")
            if _is_core_pyc(normalized, rel):
                if _exact_shim(data, extension, pyc_python=pyc_python):
                    shim_count[rel] += 1
                else:
                    leaked.append(location + " (unverified core bytecode)")

    def interesting(name: str) -> bool:
        normalized = name.replace("\\", "/")
        basename = normalized.rsplit("/", 1)[-1]
        return (any(
            (basename.startswith(ext) or normalized.endswith(rel)
             or _is_core_pyc(normalized, rel))
            for rel, _, ext, _ in CORE_LIST
        ))

    with zipfile.ZipFile(apk) as archive:
        required = ("assets/private.tar", "lib/arm64-v8a/libpybundle.so")
        for name in required:
            if name not in archive.namelist():
                raise ValueError("Missing python-for-android archive: " + name)
        for member in archive.infolist():
            if member.is_dir() or member.filename in required:
                continue
            if interesting(member.filename):
                inspect(member.filename, archive.read(member), "APK")
        for bundle in required:
            try:
                with archive.open(bundle) as stream:
                    with tarfile.open(fileobj=stream, mode="r|*") as payload:
                        for member in payload:
                            name = member.name.replace("\\", "/")
                            if (member.issym() or member.islnk() or
                                    name.startswith("/") or ".." in name.split("/")):
                                raise ValueError("Unsafe TAR member: " + bundle + ":" + name)
                            if not member.isfile() or not interesting(name):
                                continue
                            entry = payload.extractfile(member)
                            if entry is None:
                                raise ValueError("Unreadable core archive member")
                            inspect(name, entry.read(), bundle)
            except (tarfile.TarError, EOFError) as exc:
                raise ValueError("Invalid python-for-android TAR: " + bundle) from exc
    if leaked:
        raise ValueError("Phase05 core implementation leaked: " + ", ".join(leaked))
    bad = [rel for rel in native_count if native_count[rel] != 1 or shim_count[rel] != 1]
    if bad:
        raise ValueError("Missing/duplicate native Phase05 cores or shims: " + ", ".join(bad))
    return {"native_cores": native_count, "verified_shims": shim_count,
            "implementation_leaks": 0, "previous_wire_vault_audit": "passed"}


def report_apk(apk: Path, *, pyc_python: Path | None = None) -> Path:
    result = verify_apk(apk, pyc_python=pyc_python)
    output = Path(apk).parent / "PHASE05_ALL_CORES_INFO.txt"
    output.write_text(
        "WLRe_LaLa Android Phase05 P0/P1 Cython audit\n"
        "Previously native wire and vault: VERIFIED\n"
        + "\n".join(f"{rel}: VERIFIED native ARM64 extension + 1 exact shim"
                    for rel in result["native_cores"])
        + "\nPython implementations of these six cores exposed: 0\n"
        "Static ELF/shim checks do NOT prove Android runtime or data integrity.\n"
        "Cython makes analysis harder, not impossible.\n",
        encoding="utf-8",
    )
    return output



def host_compile(source: Path = ROOT) -> None:
    """Compile each P0/P1 implementation with Cython 3 on HOST, no APK.

    Build/ELF import on the Android phone is independently checked later.
    Does not touch the main checkout or any persistent signing secrets.
    """
    import tempfile

    source = source.resolve(strict=True)
    _source_check(source)
    with tempfile.TemporaryDirectory(prefix="lalaphase05-host-") as scratch:
        for rel, recipe, extension, priority in CORE_LIST:
            work = Path(scratch) / recipe
            work.mkdir()
            shutil.copy2(source / rel, work / (extension + ".pyx"))
            shutil.copy2(source / "p4a-recipes" / recipe / "setup.py", work / "setup.py")
            proc = subprocess.run(
                [sys.executable, "setup.py", "build_ext", "--inplace"],
                cwd=work, capture_output=True, text=True, timeout=300, check=False,
            )
            if proc.returncode:
                raise RuntimeError(
                    "Phase05 host Cython build failed for " + rel +
                    ": " + (proc.stdout + proc.stderr)[-2200:]
                )
            candidates = list(work.glob(extension + "*.so"))
            if len(candidates) != 1:
                raise RuntimeError("Expected one host Cython extension: " + rel)
            print(f"PASS {priority} host Cython compile: {rel}", flush=True)
    print("Host compile all P0/P1: PASS; Android ARM64 and live behavior NOT verified.")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) == 2 and argv[0] == "_verify-core-pyc":
        if argv[1] not in {extension for _, _, extension, _ in CORE_LIST}:
            return 1
        return 0 if _exact_shim(sys.stdin.buffer.read(), argv[1]) else 1
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    actions.add_parser("host-compile")
    stage_cmd = actions.add_parser("stage")
    stage_cmd.add_argument("--source", type=Path, default=ROOT)
    stage_cmd.add_argument("--output", type=Path, required=True)
    for kind in ("verify-apk", "report-apk"):
        cmd = actions.add_parser(kind)
        cmd.add_argument("apk", type=Path)
        cmd.add_argument("--pyc-python", type=Path)
    opt = parser.parse_args(argv)
    if opt.action == "host-compile":
        host_compile()
    elif opt.action == "stage":
        print(stage(opt.source, opt.output))
    elif opt.action == "verify-apk":
        print(verify_apk(opt.apk, pyc_python=opt.pyc_python))
    else:
        print(report_apk(opt.apk, pyc_python=opt.pyc_python))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
