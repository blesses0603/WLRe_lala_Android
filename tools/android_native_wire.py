"""Opt-in ARM64 Cython staging and fail-closed APK inspection.

This does NOT produce a native binary by itself. Run Buildozer in the staged
source tree using the local python-for-android recipe after unit tests pass.
"""
from __future__ import annotations

import argparse
import configparser
import importlib.util
import io
import marshal
from pathlib import Path
import re
import shutil
import subprocess
import sys
import struct
import tarfile
import types
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
PRIVATE_EXTS = frozenset({".keystore", ".jks", ".p12", ".pfx", ".pem", ".p8", ".key"})
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
            if (name in EXCLUDE_ROOTS or name.startswith(".") or path.is_symlink()
                    or path.suffix.lower() in PRIVATE_EXTS):
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
        recipe_dir = output / "p4a-recipes"
        # Buildozer may invoke python-for-android from an internal working
        # directory; a relative local_recipes path can silently miss recipes.
        text = text.replace("p4a.branch = ",
                            f"p4a.local_recipes = {recipe_dir}\np4a.branch = ", 1)
        enabled = re.search(r"(?m)^requirements = (.+)$", text)
        if (f"p4a.local_recipes = {recipe_dir}" not in text
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


def _host_only_so_name(member: str) -> bool:
    lower = member.lower()
    return any(part in lower for part in ("x86_64", "i686", "linux-gnu", "darwin", "win_amd64"))


def _arm64_elf(blob: bytes) -> bool:
    # This is a strict ELF-header sanity check, not proof of Android loader
    # compatibility. A live Android import is still mandatory for acceptance.
    return (len(blob) >= 64 and blob[:4] == b"\x7fELF"
            and blob[4] == 2 and blob[5] == 1 and blob[6] == 1
            and struct.unpack_from("<H", blob, 16)[0] == 3  # ET_DYN
            and struct.unpack_from("<H", blob, 18)[0] == 183  # EM_AARCH64
            and struct.unpack_from("<I", blob, 20)[0] == 1
            and struct.unpack_from("<H", blob, 52)[0] == 64)


def _is_wire_bytecode(name: str) -> bool:
    normalized = name.replace("\\", "/")
    return re.search(
        r"(?:^|/)wlre/network/(?:__pycache__/)?wire(?:\.cpython-\d+[a-z]*)?\.pyc$",
        normalized,
    ) is not None


def _is_exact_shim_bytecode(blob: bytes, *, pyc_python: Path | None = None) -> bool:
    if pyc_python is not None and pyc_python.resolve() != Path(sys.executable).resolve():
        # The pinned p4a Python can differ from the host used for APK audit.
        # Marshal is version-specific: delegate to the matching hostpython.
        try:
            checked = subprocess.run(
                [str(pyc_python), "-I", str(Path(__file__).resolve()), "_verify-pyc"],
                input=blob, capture_output=True, timeout=15, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        return checked.returncode == 0
    # Fail closed for unknown Python bytecode versions, damaged marshal data,
    # renamed implementation bytecode, or hand-written alternative shims.
    # Only examine own local trusted build artifacts, not arbitrary uploads.
    if len(blob) < 16 or len(blob) > 1048576 or blob[:4] != importlib.util.MAGIC_NUMBER:
        return False
    try:
        input_stream = io.BytesIO(blob[16:])
        code = marshal.load(input_stream)
    except (ValueError, EOFError, TypeError):
        return False
    if input_stream.tell() != len(blob) - 16 or not isinstance(code, types.CodeType):
        return False
    signature = lambda obj: (
        obj.co_code, obj.co_names, obj.co_consts, obj.co_varnames,
        obj.co_cellvars, obj.co_freevars,
    )
    return any(
        signature(code) == signature(compile(SHIM, "<shim>", "exec", optimize=level))
        for level in (0, 1, 2)
    )


def verify_apk(path: Path, *, pyc_python: Path | None = None) -> dict:
    """Audit actual p4a SDL2 package layout, not just outer APK files.

    The pinned python-for-android 8ef9d1d makes two gzip TAR archives:
      * assets/private.tar: application Python files, including the wire shim
      * lib/arm64-v8a/libpybundle.so: bundled site-packages, including native .so
    The second path is NOT an ELF shared library despite its .so suffix.
    """
    found, suspicious, shim_count = [], [], 0
    native_in_bundle = []

    def inspect_member(name: str, blob: bytes, *, bundle: str = ""):
        nonlocal shim_count
        location = f"{bundle}:{name}" if bundle else name
        if _candidate(name):
            if _host_only_so_name(name) or not _arm64_elf(blob):
                raise ValueError(f"Non-ARM64 native wire binary: {location}")
            found.append(location)
            if bundle == "lib/arm64-v8a/libpybundle.so":
                # This is the only supported importable location for this
                # pinned SDL2 python-for-android bootstrap.
                normalized = name.replace("\\", "/")
                if re.search(r"(?:^|/)site-packages/_wlre_wire_native(?:\.[a-zA-Z0-9_+.-]+)?\.so$", normalized):
                    native_in_bundle.append(location)
        if name.endswith(("_wlre_wire_native.py", "_wlre_wire_native.pyc",
                          "_wlre_wire_native.pyx", "wlre/network/wire.py")):
            suspicious.append(location)
        if _is_wire_bytecode(name):
            if _is_exact_shim_bytecode(blob, pyc_python=pyc_python):
                shim_count += 1
            else:
                suspicious.append(location + " (unverified wire bytecode)")

    with zipfile.ZipFile(path) as apk:
        names = apk.namelist()
        if not any(name.startswith("lib/arm64-v8a/") for name in names):
            raise ValueError("APK does not contain Android ARM64 libraries")
        required = ("assets/private.tar", "lib/arm64-v8a/libpybundle.so")
        for name in required:
            if name not in names:
                raise ValueError(f"Missing required p4a archive: {name}")

        for info in apk.infolist():
            name = info.filename
            if name in required or info.is_dir():
                continue
            if _candidate(name) or _is_wire_bytecode(name) or name.endswith(
                    ("_wlre_wire_native.py", "_wlre_wire_native.pyc",
                     "_wlre_wire_native.pyx", "wlre/network/wire.py")
            ):
                inspect_member(name, apk.read(info))

        for archive_name in required:
            try:
                with tarfile.open(fileobj=io.BytesIO(apk.read(archive_name)), mode="r:*") as archive:
                    for member in archive:
                        name = member.name.replace("\\", "/")
                        if (member.issym() or member.islnk()
                                or name.startswith("/")
                                or any(part == ".." for part in name.split("/"))):
                            raise ValueError(f"Unsafe TAR member: {archive_name}:{name}")
                        if not member.isfile():
                            continue
                        # Read only members relevant to native/shim security, not
                        # every large application dependency in the Python bundle.
                        if (_candidate(name) or _is_wire_bytecode(name)
                                or name.endswith(("_wlre_wire_native.py", "_wlre_wire_native.pyc",
                                                   "_wlre_wire_native.pyx", "wlre/network/wire.py"))):
                            inspect_member(name, archive.extractfile(member).read(),
                                           bundle=archive_name)
            except tarfile.TarError as exc:
                raise ValueError(f"Invalid python-for-android archive: {archive_name}") from exc

    if suspicious:
        raise ValueError("Native wire bundle leaks implementation: " + ", ".join(suspicious))
    if not native_in_bundle:
        raise ValueError("Missing Android ARM64 native wire extension in libpybundle.so site-packages")
    if not shim_count:
        raise ValueError("Missing verified wire import shim bytecode")
    return {"arm64_wire_extensions": found, "verified_wire_shims": shim_count, "source_leaks": 0}



def report_apk(path: Path, *, pyc_python: Path | None = None) -> Path:
    """Fail closed and persist a concise native-wire audit for signed APKs."""
    result = verify_apk(path, pyc_python=pyc_python)
    native = result["arm64_wire_extensions"]
    if len(native) != 1 or result["verified_wire_shims"] != 1 or result["source_leaks"] != 0:
        raise ValueError("Expected precisely one ARM64 native wire and one verified shim")
    output = Path(path).parent / "NATIVE_WIRE_INFO.txt"
    output.write_text(
        "WLRe_LaLa Android ARM64 Cython wire verification\\n"
        "Native wire Cython extension: VERIFIED\\n"
        "Module: _wlre_wire_native\\n"
        "ABI: arm64-v8a (AArch64 ELF64 ET_DYN)\\n"
        "Location: " + native[0] + "\\n"
        "Verified import shim bytecode: 1\\n"
        "Original wire implementation source/bytecode leaks: 0\\n"
        "All other app Python bytecode remains extractable and is not Cython protected.\\n"
        "Not proof of live Android foreground service compatibility.\\n",
        encoding="utf-8",
    )
    return output


def host_smoke(root: Path = ROOT) -> None:
    """Run the exact native shim through a host Cython build in disposable dirs.

    This test does NOT establish Android NDK compatibility and cannot be used
    to satisfy the ARM64 APK acceptance gate.
    """
    import json
    import os
    import subprocess
    import sys
    import tempfile

    root = root.resolve(strict=True)
    _assert_clean_source(root)
    with tempfile.TemporaryDirectory(prefix="lalawire-native-host-") as tmp:
        test_root = Path(tmp)
        native = test_root / "recipe"
        native.mkdir()
        shutil.copy2(root / WIRE_REL, native / f"{NATIVE_BASENAME}.pyx")
        shutil.copy2(root / RECIPE_ROOT / "setup.py", native / "setup.py")
        subprocess.run(
            [sys.executable, "setup.py", "build_ext", "--inplace"],
            cwd=native, check=True, capture_output=True, text=True, timeout=180,
        )
        built = list(native.glob(f"{NATIVE_BASENAME}*.so"))
        if len(built) != 1:
            raise RuntimeError("Expected exactly one compiled host Cython extension")
        stage_root = test_root / "app"
        (stage_root / "wlre/network").mkdir(parents=True)
        (stage_root / "wlre/__init__.py").write_text("", encoding="utf-8")
        (stage_root / "wlre/network/__init__.py").write_text("", encoding="utf-8")
        (stage_root / WIRE_REL).write_text(SHIM, encoding="utf-8")
        shutil.copy2(built[0], stage_root / built[0].name)
        code = (
            "from tools.android_cython_wire import snapshot\n"
            "import importlib, importlib.machinery, json, sys\n"
            "sys.path.insert(0, sys.argv[1])\n"
            "w = importlib.import_module('wlre.network.wire')\n"
            "mod = importlib.import_module(w.Packet.__module__)\n"
            "native = any(mod.__file__.endswith(x) for x in importlib.machinery.EXTENSION_SUFFIXES)\n"
            "print(json.dumps({'native': native, 'contract': snapshot(w)}, sort_keys=True))\n"
        )

        def run(location):
            env = os.environ.copy()
            env["PYTHONPATH"] = str(root)
            result = subprocess.run(
                [sys.executable, "-c", code, str(location)],
                cwd=test_root, env=env, capture_output=True, text=True, check=True, timeout=30,
            )
            return json.loads(result.stdout)

        pure = run(root)
        compiled = run(stage_root)
        if pure["native"] or not compiled["native"]:
            raise AssertionError("Native shim smoke imported an unexpected implementation")
        if pure["contract"] != compiled["contract"]:
            raise AssertionError("Cython shim changed wire protocol contract")
    print("PASS: host Cython extension + production-style shim parity. Android ARM64 NOT verified.")

def main(argv=None):
    if sys.argv[1:] == ["_verify-pyc"]:
        return 0 if _is_exact_shim_bytecode(sys.stdin.buffer.read()) else 1
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="operation", required=True)
    staging = sub.add_parser("stage")
    staging.add_argument("--source", type=Path, default=ROOT)
    staging.add_argument("--output", type=Path, required=True)
    sub.add_parser("host-smoke")
    audit = sub.add_parser("verify-apk")
    report = sub.add_parser("report-apk")
    for verifier in (audit, report):
        verifier.add_argument("apk", type=Path)
        verifier.add_argument("--pyc-python", type=Path,
                              help="Matching hostpython for target p4a CPython bytecode (e.g. Python 3.14)")
    opts = parser.parse_args(argv)
    if opts.operation == "stage":
        print(stage(opts.source, opts.output))
    elif opts.operation == "host-smoke":
        host_smoke()
    elif opts.operation == "report-apk":
        print(report_apk(opts.apk, pyc_python=opts.pyc_python))
    else:
        print(verify_apk(opts.apk, pyc_python=opts.pyc_python))


if __name__ == "__main__":
    sys.exit(main())
