"""Phase07 Android runtime certificate pin injected into a disposable native stage.

The pin is a *public* SHA-256 certificate fingerprint. No keystore or private
signature material is copied to the application source/staging tree.
Only trusted main/tag Android releases execute this stage command.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import sys
import zipfile

if __package__ in ("", None):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.android_signing import _fingerprint

RELATIVE_JAVA = Path("android_app/java/org/lala/client/RuntimeIntegrity.java")
PLACEHOLDER = "__WLRE_SIGNER_PIN__"
PACKAGE = "org.lala.client.wlrelala"


def pin_stage(stage: Path, public_pin: str | None = None, *, source: Path | None = None) -> Path:
    """Inject only a validated PUBLIC fingerprint; refuse modifying repo sources."""
    stage = Path(stage).resolve(strict=True)
    source = (Path(__file__).resolve().parents[1] if source is None else Path(source)).resolve()
    if stage == source or source in stage.parents:
        raise ValueError("Runtime pin staging must be outside the source checkout")
    pin = _fingerprint(os.environ.get("ANDROID_EXPECTED_SIGNER_SHA256", "") if public_pin is None else public_pin)
    path = stage / RELATIVE_JAVA
    if path.is_symlink() or not path.is_file():
        raise ValueError("Phase07 Java runtime integrity guard not staged")
    if path.resolve().parent != (stage / RELATIVE_JAVA.parent).resolve():
        raise ValueError("Runtime guard staging path is unsafe")
    contents = path.read_text(encoding="utf-8")
    if contents.count(PLACEHOLDER) != 1:
        raise ValueError("Runtime signer placeholder missing or duplicated")
    if ('EXPECTED_PACKAGE = "' + PACKAGE + '"') not in contents:
        raise ValueError("Runtime integrity package identifier mismatch")
    if "PackageManager.GET_SIGNING_CERTIFICATES" not in contents:
        raise ValueError("Runtime signature verifier cannot be bypassed during packaging")
    replaced = contents.replace(PLACEHOLDER, pin)
    # Atomic file replacement; do not expose signing secrets or print data.
    temporary = path.with_name(path.name + ".new")
    if temporary.exists() or temporary.is_symlink():
        raise ValueError("Runtime stage temporary target exists")
    try:
        temporary.write_text(replaced, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
    verify_stage(stage, pin)
    return path


def verify_stage(stage: Path, public_pin: str | None = None) -> bool:
    """Check the exact staged package and certificate pin used by Java."""
    stage = Path(stage).resolve(strict=True)
    pin = _fingerprint(os.environ.get("ANDROID_EXPECTED_SIGNER_SHA256", "") if public_pin is None else public_pin)
    path = stage / RELATIVE_JAVA
    if path.is_symlink() or not path.is_file():
        raise ValueError("Runtime signer Java source missing")
    contents = path.read_text(encoding="utf-8")
    if PLACEHOLDER in contents:
        raise ValueError("Runtime signer Java source still contains placeholder")
    if contents.count('EXPECTED_CERT_SHA256 = "' + pin + '"') != 1:
        raise ValueError("Staged runtime signer pin differs from signed APK policy")
    if ('EXPECTED_PACKAGE = "' + PACKAGE + '"') not in contents:
        raise ValueError("Runtime package mismatch")
    return True


def verify_compiled_guard(apk: Path, public_pin: str | None = None) -> bool:
    """Require the public pin in the compiled DEX (not only staged Java).

    Does not replace apksigner verification or Android real-device acceptance.
    """
    pin = _fingerprint(os.environ.get("ANDROID_EXPECTED_SIGNER_SHA256", "")
                       if public_pin is None else public_pin)
    with zipfile.ZipFile(apk) as contents:
        dex = [item for item in contents.infolist()
               if item.filename == "classes.dex"
               or (item.filename.startswith("classes")
                   and item.filename.endswith(".dex")
                   and item.filename[7:-4].isdigit())]
        if not dex:
            raise ValueError("APK has no compiled Android DEX")
        found = False
        for member in dex:
            data = contents.read(member)
            if PLACEHOLDER.encode("ascii") in data:
                raise ValueError("APK contains unpinned runtime integrity placeholder")
            if pin.encode("ascii") in data:
                found = True
        if not found:
            raise ValueError("Compiled Android APK lacks Phase07 runtime certificate pin")
    return True


def report(output_directory: Path, stage: Path, public_pin: str | None = None) -> Path:
    """Evidence of source-level pinning, not a substitute for device tests."""
    verify_stage(stage, public_pin)
    built = list(Path(output_directory).glob("*.apk"))
    if len(built) != 1:
        raise ValueError("Expected one signed APK for Phase07 compiled guard audit")
    verify_compiled_guard(built[0], public_pin)
    output = Path(output_directory) / "RUNTIME_INTEGRITY_INFO.txt"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "WLRe_LaLa Android Phase07 runtime integrity\n"
        "Staged Java package and public signer certificate pin: VERIFIED\n"
        "Compiled APK DEX contains runtime signer pin: VERIFIED\n"
        "Final APK certificate identity: independently verified in SIGNING_INFO.txt\n"
        "Activity and foreground service invoke runtime signer verification before sessions.\n"
        "No private key is embedded in the runtime verifier.\n"
        "Physical Android device, smali patching, hooks, and root bypass: NOT VERIFIED.\n"
        "A client-side guard is defense-in-depth, NOT server-backed attestation.\n",
        encoding="utf-8",
    )
    return output


def main(args=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare-stage", "verify-stage", "report"))
    parser.add_argument("stage", type=Path)
    parser.add_argument("output_directory", type=Path, nargs="?")
    opts = parser.parse_args(args)
    if opts.action == "prepare-stage":
        pin_stage(opts.stage)
        print("Phase07 runtime Java public signer pin staged; private key not accessed.")
    elif opts.action == "verify-stage":
        verify_stage(opts.stage)
        print("Phase07 runtime signer pin and Android package verified in staging.")
    else:
        if opts.output_directory is None:
            parser.error("report needs an output directory")
        report(opts.output_directory, opts.stage)
        print("Phase07 runtime build evidence written (not real-device attestation).")


if __name__ == "__main__":
    main()
