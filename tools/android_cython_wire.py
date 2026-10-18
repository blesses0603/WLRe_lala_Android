"""Phase 04 laboratory: compare the current wire.py with a *host* Cython build.

No Android APK, signing secret, or repository file is modified. A Linux .so
is NEVER accepted as evidence of an ARM64 Android-native extension.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SOURCE = ROOT / "wlre/network/wire.py"
EXPORTS = ("ProtocolError", "Reader", "Writer", "Packet", "encode", "FrameDecoder")


def snapshot(wire):
    """Deterministic API/byte-level contract; safe synthetic packets only."""
    def error(fn):
        try:
            fn()
        except Exception as exc:
            return [type(exc).__name__, str(exc)]
        raise AssertionError("Expected exception was not raised")

    a = wire.Packet(63, 7, b"\x01\x00")
    b = wire.Packet(6, 1, b"\x04\x02\x08\x06")
    stream = wire.encode(a) + wire.encode(b)
    decoder = wire.FrameDecoder()
    received = []
    for part in (stream[:1], stream[1:3], stream[3:6], stream[6:12], stream[12:]):
        received.extend(decoder.feed(part))
    decoder.finish()
    unicode_reader = wire.Reader(b"\x04A\x00B\x00")
    text = unicode_reader.unicode8()
    unicode_reader.end()
    mixed = wire.Reader(b"\x01\x02\x00\x03\x00\x00\x00")
    values = [mixed.u8(), mixed.u16(), mixed.u32()]
    mixed.end()
    return {
        "exports": [hasattr(wire, name) for name in EXPORTS],
        "packet_equality": a == wire.Packet.from_body(a.body()),
        "packet_body": a.body().hex(),
        "encoded": wire.encode(a).hex(),
        "other_xor": wire.encode(a, 0).hex(),
        "split_frames": [p.body().hex() for p in received],
        "decoded_text": text,
        "reader_numbers": values,
        "writer": wire.Writer().u8(1).u16(0x1234).u32(0x87654321).build().hex(),
        "errors": {
            "truncated_packet": error(lambda: wire.Packet.from_body(b"\x01")),
            "negative_take": error(lambda: wire.Reader(b"").take(-1)),
            "invalid_unicode": error(lambda: wire.Reader(b"\x02\x00\xd8").unicode8()),
            "odd_unicode": error(lambda: wire.Reader(b"\x01x").unicode8()),
            "invalid_integer": error(lambda: wire.Writer().u8(256)),
            "bad_magic": error(lambda: wire.FrameDecoder().feed(b"\x00" * 4)),
            "bad_length": error(lambda: wire.FrameDecoder(0).feed(b"\xc4\xc6\x01\x00")),
            "invalid_xor": error(lambda: wire.FrameDecoder(256)),
            "incomplete_frame": error(lambda: (lambda d: (d.feed(b"\x01"), d.finish()))(wire.FrameDecoder())),
            "too_long": error(lambda: wire.encode(wire.Packet(1, 2, b"x" * 65534))),
        },
    }


def prepare_package(destination):
    package = destination / "wlre/network"
    package.mkdir(parents=True)
    (destination / "wlre/__init__.py").write_text("", encoding="utf-8")
    (package / "__init__.py").write_text("", encoding="utf-8")
    shutil.copy2(SOURCE, package / "wire.py")


def probe_package(destination, *, expect_native):
    probe = '''import importlib, importlib.machinery, json
from tools.android_cython_wire import snapshot
w = importlib.import_module("wlre.network.wire")
print(json.dumps({"native": any(w.__file__.endswith(s) for s in importlib.machinery.EXTENSION_SUFFIXES), "result": snapshot(w)}, sort_keys=True, ensure_ascii=False))'''
    env = os.environ.copy()
    env["PYTHONPATH"] = str(destination) + os.pathsep + str(ROOT)
    completed = subprocess.run([sys.executable, "-c", probe], cwd=destination,
                               env=env, check=True, capture_output=True, text=True, timeout=30)
    data = json.loads(completed.stdout)
    if data["native"] != expect_native:
        raise RuntimeError("Module import selected the wrong backend")
    return data["result"]


def host_smoke():
    """Build in a disposable host directory. Not suitable for Android packaging."""
    if not SOURCE.is_file():
        raise FileNotFoundError(SOURCE)
    with tempfile.TemporaryDirectory(prefix="lala-cython-wire-") as folder:
        temporary = Path(folder)
        pure, native = temporary / "pure", temporary / "native"
        for directory in (pure, native):
            prepare_package(directory)
        (native / "setup.py").write_text(
            'from setuptools import Extension, setup\n'
            'from Cython.Build import cythonize\n'
            'setup(name="lala-wire-host-only", ext_modules=cythonize('
            '[Extension("wlre.network.wire", ["wlre/network/wire.py"])], '
            'compiler_directives={"language_level": 3}))\n', encoding="utf-8")
        subprocess.run([sys.executable, "setup.py", "build_ext", "--inplace"],
                       cwd=native, check=True, capture_output=True, text=True, timeout=180)
        (native / "wlre/network/wire.py").unlink()
        baseline = probe_package(pure, expect_native=False)
        compiled = probe_package(native, expect_native=True)
        if baseline != compiled:
            raise AssertionError("Cython host build changed wire.py protocol contract:\n" +
                                 json.dumps({"python": baseline, "cython": compiled},
                                            indent=2, ensure_ascii=False))
    print("PASS: Python/Cython host probe parity. Android ARM64 NOT verified.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host-smoke", action="store_true",
                        help="Compile disposable host Cython extension and compare synthetic vectors")
    args = parser.parse_args(argv)
    if args.host_smoke:
        host_smoke()
    else:
        from wlre.network import wire
        result = snapshot(wire)
        if not all(result["exports"]) or not result["packet_equality"]:
            raise AssertionError("Pure Python wire baseline is incomplete")
        print("PASS: Pure Python wire contract (native compilation not requested).")


if __name__ == "__main__":
    main()
