"""Phase05 P0 Android vault Cython pilot; preserve Phase04 wire implementation.

The app checkout remains Python-only. Only disposable stage inputs contain the
native vault shim. The verifier requires an Android ARM64 Cython extension
in p4a site-packages AND exact shim bytecode, not just a successful APK build.
"""
from __future__ import annotations

import argparse
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

from tools.android_native_wire import (
    _arm64_elf, _host_only_so_name, stage as stage_wire,
    verify_apk as verify_wire_apk,
)

ROOT = Path(__file__).resolve().parents[1]
VAULT_REL = Path("android_app/vault.py")
RECIPE_REL = Path("p4a-recipes/lalavault")
EXTENSION = "_wlre_vault_native"
SHIM = (
    '"""Android P0 vault interface; implementation lives in ARM64 native extension."""\n'
    "from _wlre_vault_native import AndroidCipher, AccountVault\n"
    '__all__ = ["AndroidCipher", "AccountVault"]\n'
)


def stage(source: Path, output: Path) -> Path:
    """Native wire remains as-is; add ONLY vault to a disposable native stage."""
    source = source.resolve(strict=True)
    target = source / VAULT_REL
    recipe = source / RECIPE_REL
    for needed in (target, recipe / "__init__.py", recipe / "setup.py"):
        if not needed.is_file() or needed.is_symlink():
            raise ValueError("Missing or symlinked Phase05 vault source/recipe: " + str(needed))
    if not target.read_bytes().startswith(b'"""Android-private ciphertext store;'):
        raise ValueError("Unexpected P0 Android vault baseline")
    stage_wire(source, output)
    output = output.resolve()
    try:
        staged = output / VAULT_REL
        native = output / RECIPE_REL / "src" / (EXTENSION + ".pyx")
        native.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(staged, native)
        shutil.copy2(output / RECIPE_REL / "setup.py", native.parent / "setup.py")
        staged.write_text(SHIM, encoding="utf-8")
        spec = output / "buildozer.spec"
        contents = spec.read_text(encoding="utf-8")
        matched = re.search(r"(?m)^requirements\s*=\s*(.+)$", contents)
        if not matched or "lalawire" not in matched.group(1).split(","):
            raise ValueError("Phase04 wire prerequisite missing in staging")
        if "lalavault" in matched.group(1):
            raise ValueError("Vault recipe added more than once")
        contents = contents[:matched.end()] + ",lalavault" + contents[matched.end():]
        spec.write_text(contents, encoding="utf-8")
        return output
    except Exception:
        shutil.rmtree(output, ignore_errors=True)
        raise


def _native_candidate(name: str) -> bool:
    return re.fullmatch(r"_wlre_vault_native(?:\.[A-Za-z0-9_+.-]+)?\.so",
                        name.replace("\\", "/").rsplit("/", 1)[-1]) is not None


def _vault_pyc(name: str) -> bool:
    normalized = name.replace("\\", "/")
    return re.search(
        r"(?:^|/)android_app/(?:__pycache__/)?vault(?:\.cpython-\d+[a-z]*)?\.pyc$",
        normalized,
    ) is not None


def _exact_shim(blob: bytes, *, pyc_python: Path | None = None) -> bool:
    if pyc_python is not None and pyc_python.resolve() != Path(sys.executable).resolve():
        try:
            checked = subprocess.run(
                [str(pyc_python), "-I", str(Path(__file__).resolve()), "_verify-vault-pyc"],
                input=blob, capture_output=True, timeout=15, check=False,
            )
            return checked.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            return False
    if len(blob) < 16 or len(blob) > 1048576 or blob[:4] != importlib.util.MAGIC_NUMBER:
        return False
    try:
        stream = io.BytesIO(blob[16:])
        code = marshal.load(stream)
    except (EOFError, ValueError, TypeError):
        return False
    if stream.tell() != len(blob) - 16 or not isinstance(code, types.CodeType):
        return False

    def signature(obj):
        return (obj.co_code, obj.co_names, obj.co_consts, obj.co_varnames,
                obj.co_cellvars, obj.co_freevars)

    return any(signature(code) == signature(compile(SHIM, "<vault-shim>", "exec", optimize=opt))
               for opt in (0, 1, 2))


def verify_apk(apk: Path, *, pyc_python: Path | None = None) -> dict:
    """Require both Phase04 wire and Phase05 vault native cores in same APK."""
    verify_wire_apk(apk, pyc_python=pyc_python)
    native = []
    shim_count = 0
    leaked = []

    def inspect(name: str, data: bytes, container: str):
        nonlocal shim_count
        normal = name.replace("\\", "/")
        loc = container + ":" + normal
        basename = normal.rsplit("/", 1)[-1]
        if _native_candidate(normal):
            if _host_only_so_name(normal) or not _arm64_elf(data):
                raise ValueError("Non-ARM64 native vault binary: " + loc)
            if container == "lib/arm64-v8a/libpybundle.so" and re.search(
                r"(?:^|/)site-packages/_wlre_vault_native(?:\.[A-Za-z0-9_+.-]+)?\.so$",
                normal,
            ):
                native.append(loc)
            else:
                leaked.append(loc + " (duplicate or non-importable extension)")
        if basename in ("_wlre_vault_native.py", "_wlre_vault_native.pyx",
                        "_wlre_vault_native.pyc") or normal.endswith("android_app/vault.py"):
            leaked.append(loc + " (native implementation source)")
        if _vault_pyc(normal):
            if _exact_shim(data, pyc_python=pyc_python):
                shim_count += 1
            else:
                leaked.append(loc + " (unverified vault bytecode)")

    with zipfile.ZipFile(apk) as archive:
        for name in ("assets/private.tar", "lib/arm64-v8a/libpybundle.so"):
            if name not in archive.namelist():
                raise ValueError("Missing python-for-android archive: " + name)
        for info in archive.infolist():
            if info.is_dir() or info.filename in ("assets/private.tar", "lib/arm64-v8a/libpybundle.so"):
                continue
            n = info.filename
            if _native_candidate(n) or _vault_pyc(n) or n.endswith(
                ("android_app/vault.py", "_wlre_vault_native.py",
                 "_wlre_vault_native.pyx", "_wlre_vault_native.pyc")
            ):
                inspect(n, archive.read(info), "APK")
        for archive_name in ("assets/private.tar", "lib/arm64-v8a/libpybundle.so"):
            try:
                with tarfile.open(fileobj=io.BytesIO(archive.read(archive_name)), mode="r:*") as payload:
                    for member in payload:
                        n = member.name.replace("\\", "/")
                        if member.issym() or member.islnk() or n.startswith("/") or ".." in n.split("/"):
                            raise ValueError("Unsafe TAR member: " + archive_name + ":" + n)
                        if not member.isfile():
                            continue
                        if _native_candidate(n) or _vault_pyc(n) or n.endswith(
                            ("android_app/vault.py", "_wlre_vault_native.py",
                             "_wlre_vault_native.pyx", "_wlre_vault_native.pyc")
                        ):
                            contents = payload.extractfile(member)
                            if contents is None:
                                raise ValueError("Unable to inspect native vault member")
                            inspect(n, contents.read(), archive_name)
            except tarfile.TarError as exc:
                raise ValueError("Invalid python-for-android archive: " + archive_name) from exc

    if leaked:
        raise ValueError("Native vault bundle leaks implementation: " + ", ".join(leaked))
    if len(native) != 1 or shim_count != 1:
        raise ValueError(
            "Expected one importable ARM64 native vault and one verified shim, "
            f"found native={len(native)} shim={shim_count}"
        )
    return {"arm64_vault_extensions": native, "verified_vault_shims": shim_count,
            "vault_implementation_leaks": 0}


def report_apk(apk: Path, *, pyc_python: Path | None = None) -> Path:
    result = verify_apk(apk, pyc_python=pyc_python)
    output = Path(apk).parent / "NATIVE_VAULT_INFO.txt"
    output.write_text(
        "WLRe_LaLa Android Phase05 native vault audit\n"
        "P0 Android Keystore bridge implementation: ARM64 Cython extension VERIFIED\n"
        "Module: _wlre_vault_native\n"
        "Native file: " + result["arm64_vault_extensions"][0] + "\n"
        "Import shim verified: 1\n"
        "Original vault Python implementation source/bytecode leaks: 0\n"
        "Existing wire native audit: PASSED\n"
        "Live Android Keystore JNI and in-place upgrade: NOT PROVEN BY STATIC AUDIT\n",
        encoding="utf-8",
    )
    return output



def host_smoke(source: Path = ROOT) -> None:
    """Compare pure Python against a REAL host Cython vault extension.

    The JNI-backed AndroidCipher constructor intentionally remains a device test.
    This checks AccountVault file persistence, tamper handling and class exports.
    """
    import json
    import os
    import tempfile

    source = source.resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="lalavault-host-smoke-") as temp:
        folder = Path(temp)
        build = folder / "build"
        build.mkdir()
        shutil.copy2(source / VAULT_REL, build / (EXTENSION + ".pyx"))
        shutil.copy2(source / RECIPE_REL / "setup.py", build / "setup.py")
        command = subprocess.run(
            [sys.executable, "setup.py", "build_ext", "--inplace"],
            cwd=build, text=True, capture_output=True, timeout=180, check=False,
        )
        if command.returncode:
            raise RuntimeError("Host vault Cython compilation failed: "
                               + command.stderr[-1600:])
        built = list(build.glob(EXTENSION + "*.so"))
        if len(built) != 1:
            raise RuntimeError("Expected exactly one host native vault extension")
        package = folder / "app"
        (package / "android_app").mkdir(parents=True)
        (package / "android_app/__init__.py").write_text("", encoding="utf-8")
        (package / VAULT_REL).write_text(SHIM, encoding="utf-8")
        shutil.copy2(built[0], package / built[0].name)

        snapshot_code = r'''
import base64
import hashlib
import json
from pathlib import Path
import sys
import tempfile
sys.path.insert(0, sys.argv[1])
from android_app.vault import AccountVault, AndroidCipher

class DeterministicCipher:
    def encrypt(self, plain):
        return {"data": base64.b64encode(plain).decode("ascii"),
                "digest": hashlib.sha256(plain).hexdigest()}
    def decrypt(self, record):
        plain = base64.b64decode(record["data"])
        if hashlib.sha256(plain).hexdigest() != record["digest"]:
            raise ValueError("tampered")
        return plain

with tempfile.TemporaryDirectory() as temp:
    path = Path(temp) / "vault.json"
    vault = AccountVault(path, DeterministicCipher())
    before = vault.load()
    records = [{"account": "測試-甲", "line": 3}, {"account": "B", "line": 0}]
    vault.save(records)
    after = vault.load()
    fresh = AccountVault(path, DeterministicCipher()).load()
    vault.save([])
    cleared = vault.load()
    path.write_text('{"data":"YWJj","digest":"wrong"}', encoding="utf-8")
    tamper = False
    try:
        vault.load()
    except ValueError:
        tamper = True
    print(json.dumps({
        "native": AndroidCipher.__module__ == "_wlre_vault_native",
        "before": before, "after": after, "fresh": fresh,
        "cleared": cleared, "tamper_rejected": tamper,
        "classes": sorted([AndroidCipher.__name__, AccountVault.__name__])
    }, ensure_ascii=False, sort_keys=True))
'''
        def run(location: Path):
            env = os.environ.copy()
            env["PYTHONPATH"] = str(source)
            result = subprocess.run(
                [sys.executable, "-c", snapshot_code, str(location)],
                cwd=folder, env=env, capture_output=True, text=True,
                timeout=30, check=True,
            )
            return json.loads(result.stdout)

        pure, compiled = run(source), run(package)
        if pure.pop("native") is not False or compiled.pop("native") is not True:
            raise AssertionError("Vault smoke did not import the expected implementation")
        if pure != compiled or not pure["tamper_rejected"]:
            raise AssertionError("Cython changed the P0 vault storage contract")
    print("PASS: P0 vault host Cython/native shim parity; Android JNI unverified.")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv == ["_verify-vault-pyc"]:
        return 0 if _exact_shim(sys.stdin.buffer.read()) else 1
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("host-smoke")
    cmd_stage = sub.add_parser("stage")
    cmd_stage.add_argument("--source", type=Path, default=ROOT)
    cmd_stage.add_argument("--output", type=Path, required=True)
    for command in ("verify-apk", "report-apk"):
        part = sub.add_parser(command)
        part.add_argument("apk", type=Path)
        part.add_argument("--pyc-python", type=Path)
    args = parser.parse_args(argv)
    if args.action == "stage":
        print(stage(args.source, args.output))
    elif args.action == "host-smoke":
        host_smoke()
    elif args.action == "verify-apk":
        print(verify_apk(args.apk, pyc_python=args.pyc_python))
    else:
        print(report_apk(args.apk, pyc_python=args.pyc_python))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
