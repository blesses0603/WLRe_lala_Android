"""Fail-closed Android packaging checks; not a substitute for source obfuscation.

Checks for accidental private-key/credential distribution and unsafe Buildozer
options. No private data is ever printed. This does not hide bytecode in APKs or establish repository access controls.
"""
import configparser
from pathlib import Path
import re
import sys
import tarfile
import zipfile

if __package__ in (None, ""):
    from android_archive_audit import audit_apk
else:
    from .android_archive_audit import audit_apk


ROOT = Path(__file__).resolve().parents[1]
DANGEROUS_NAMES = {
    ".env", ".env.production", ".env.local", "id_rsa", "id_ed25519",
    "google-services.json", "service-account.json", "credentials.json",
}
DANGEROUS_SUFFIXES = {
    ".keystore", ".jks", ".p12", ".pfx", ".pem", ".p8", ".key", ".asc",
}
REQUIRED_EXCLUSIONS = {".git", ".github", "tests", "tools", ".buildozer", "bin"}
KEY_MATERIAL = re.compile(
    rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"
    rb"|-----BEGIN ENCRYPTED" + rb" PRIVATE KEY-----"
    rb"|AKIA[A-Z0-9]{16}"
    rb"|gh(?:p|o|u|s|r)_[A-Za-z0-9_]{30,}"
)
SCANNED_SUFFIXES = {".py", ".java", ".json", ".yml", ".yaml", ".spec", ".properties"}
MAX_TEXT_SCAN = 2 * 1024 * 1024
# Phase 03 is an inventory and fail-closed packaging gate. No Cython yet.
HIGH_RISK_CORE = {
    "android_app/vault.py": "account encryption boundary",
    "android_app/runtime.py": "private IPC and authorization boundary",
    "android_app/sessions.py": "account/session lifecycle",
    "wlre/network/client.py": "network login and credentials flow",
    "wlre/network/protocol.py": "game packet commands and login encoding",
    "wlre/network/wire.py": "game wire framing and codec",
}
FOLLOWUP_CORE = {
    "wlre/services/battle/auto_battle.py": "game automation decisions",
    "wlre/services/expedition.py": "expedition orchestration",
}
APP_SOURCE_PREFIXES = ("android_app/", "wlre/")


def _sensitive_filename(name):
    name = name.replace("\\", "/")
    parts = [x.lower() for x in name.split("/") if x]
    return any(part in DANGEROUS_NAMES or
               Path(part).suffix.lower() in DANGEROUS_SUFFIXES
               for part in parts)


def _spec_options(spec):
    config = configparser.ConfigParser(interpolation=None)
    if not config.read(spec, encoding="utf-8"):
        raise ValueError("buildozer.spec not found")
    return config["app"]


def check_configuration(root=ROOT):
    root = Path(root)
    app = _spec_options(root / "buildozer.spec")
    if app.get("android.allow_backup", "").strip().lower() != "false":
        raise ValueError("Android backups must remain disabled for game credentials")
    if app.get("source.dir", "").strip() != ".":
        raise ValueError("Review source.dir before packaging private files")
    excludes = {x.strip() for x in app.get("source.exclude_dirs", "").split(",")}
    if not REQUIRED_EXCLUSIONS.issubset(excludes):
        raise ValueError("Buildozer excludes are missing required development folders")
    if "android_app" in excludes or "wlre" in excludes:
        raise ValueError("App core must remain in source for supported debug builds")
    if app.get("android.minapi", "").strip() != "31":
        raise ValueError("Android minimum API must remain 31 (Android 12)")
    if app.get("android.archs", "").strip() != "arm64-v8a":
        raise ValueError("Android builds must remain ARM64-only")
    return True


def check_files(root=ROOT):
    """Inspect project sources without echoing any matched private key content."""
    root = Path(root)
    # Restrict to paths that will be distributed or affect build scripts.
    for directory in ("android_app", "wlre", "tools"):
        folder = root / directory
        if not folder.is_dir():
            raise ValueError("Required app source missing: " + directory)
        for path in folder.rglob("*"):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            relative = path.relative_to(root).as_posix()
            if _sensitive_filename(relative):
                raise ValueError("Potential private credential file in source tree: "
                                 + relative)
            if path.suffix.lower() not in SCANNED_SUFFIXES:
                continue
            if path.stat().st_size > MAX_TEXT_SCAN:
                continue
            with path.open("rb") as stream:
                data = stream.read(MAX_TEXT_SCAN + 1)
            if KEY_MATERIAL.search(data):
                raise ValueError("Private credential material in project source: "
                                 + relative)
    entry = root / "main.py"
    if entry.is_file() and entry.stat().st_size <= MAX_TEXT_SCAN:
        if KEY_MATERIAL.search(entry.read_bytes()):
            raise ValueError("Private credential material in project source: main.py")
    for path in root.iterdir():
        if path.is_file() and _sensitive_filename(path.name):
            raise ValueError("Potential private credential file at project root: "
                             + path.name)
    return True


def inspect_apk(apk):
    """Audit APK and the python-for-android private.tar payload by member names.

    The private.tar is usually gzip-compressed despite its .tar suffix.
    Never extract untrusted members to disk, nor print member contents.
    """
    apk = Path(apk)
    if not apk.is_file():
        raise ValueError("Android APK not found")
    counts = {"python_source": 0, "python_bytecode": 0,
              "private_tar": False, "native_arm64_libraries": 0,
              "app_bytecode": 0, "high_risk_bytecode": 0,
              "non_arm64_libraries": 0}
    def record(name):
        normalized = name.replace("\\", "/")
        if (normalized.startswith("/") or
                ".." in normalized.split("/") or
                not normalized.strip("./")):
            raise ValueError("Unsafe APK archive member name")
        normalized = normalized.removeprefix("./")
        if _sensitive_filename(normalized):
            raise ValueError("APK contains a possible private credential file: " + normalized)
        lower = normalized.lower()
        application_code = (lower.startswith(APP_SOURCE_PREFIXES) or
                            lower == "main.py" or lower == "main.pyc")
        if lower.endswith(".py"):
            counts["python_source"] += 1
            if application_code:
                raise ValueError("Uncompiled application Python source in APK: " + normalized)
        elif lower.endswith((".pyc", ".pyo")):
            counts["python_bytecode"] += 1
            if application_code:
                counts["app_bytecode"] += 1
            for source in HIGH_RISK_CORE:
                module = source[:-3]
                parent, stem = module.rsplit("/", 1)
                if (lower in (module + ".pyc", module + ".pyo") or
                        (lower.startswith(parent + "/__pycache__/" + stem + ".") and
                         lower.endswith((".pyc", ".pyo")))):
                    counts["high_risk_bytecode"] += 1
                    break

    with zipfile.ZipFile(apk) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            record(info.filename)
            if info.filename.startswith("lib/arm64-v8a/") and info.filename.endswith(".so"):
                counts["native_arm64_libraries"] += 1
            elif info.filename.startswith("lib/") and info.filename.endswith(".so"):
                counts["non_arm64_libraries"] += 1
        if counts["non_arm64_libraries"]:
            raise ValueError("APK contains native libraries outside ARM64 ABI")
        if "assets/private.tar" in archive.namelist():
            counts["private_tar"] = True
            with archive.open("assets/private.tar") as payload:
                try:
                    # Streaming mode supports both plain TAR and gzip-compressed TAR.
                    with tarfile.open(fileobj=payload, mode="r|*") as members:
                        for member in members:
                            if member.issym() or member.islnk():
                                raise ValueError("Linked members are forbidden in APK private.tar")
                            if member.isfile():
                                record(member.name)
                except (tarfile.TarError, EOFError, OSError) as exc:
                    raise ValueError("Unable to audit embedded assets/private.tar") from exc
    # Phase06 second pass: inspect nested ZIP/TAR, p4a site-packages archive,
    # known private credential headers and rejected archive paths/types.
    # Native (.so) content and oversized binary blobs remain out of scope.
    from tools.android_archive_audit import _public_ca_bundle_path
    def nested_name(name):
        normalized = name.replace("\\", "/").removeprefix("./")
        if _sensitive_filename(normalized) and not _public_ca_bundle_path(normalized):
            raise ValueError("Nested APK contains potential credential filename")
        if (normalized.startswith(APP_SOURCE_PREFIXES) or normalized == "main.py"):
            if normalized.endswith(".py"):
                raise ValueError("Uncompiled application Python in nested APK archive")

    counts.update(audit_apk(apk, inspect_name=nested_name))
    return counts


def check_apk(apk):
    """Reject sensitive file names, including inside assets/private.tar."""
    inspect_apk(apk)
    return True


def report(apk):
    counts = inspect_apk(apk)
    output = Path(apk).parent / "PROTECTION_INFO.txt"
    output.write_text(
        "WLRe_LaLa Android build security summary\n"
        "APK credential filename audit (including private.tar): PASSED\n"
        "Embedded private.tar inspected: " + str(counts["private_tar"]) + "\n"
        "Bundled Python source (.py): " + str(counts["python_source"]) + "\n"
        "Bundled Python bytecode (.pyc/.pyo): " + str(counts["python_bytecode"]) + "\n"
        "Application Python bytecode still exposed: " + str(counts["app_bytecode"]) + "\n"
        "High-risk core bytecode still exposed: " + str(counts["high_risk_bytecode"]) + "\n"
        "Phase 03 application .py source leakage gate: PASSED\n"
        "ARM64 shared libraries (not proof of Cython): " +
            str(counts["native_arm64_libraries"]) + "\n"
        "Python bytecode can be extracted and analyzed; no obfuscation is claimed.\n"
        "Account vault at rest: Android Keystore with AES-GCM\n"
        "Build flavor: DEBUG test APK (NOT a store-ready release)\n"
        "Cython ARM64 wire core: see NATIVE_WIRE_INFO.txt for independent native audit\n"
        "Phase05 P0/P1 core protection: see independent PHASE05_ALL_CORES_INFO.txt audit\n"
        "Anti-tamper runtime protection: NOT enabled\n"
        "APK signature certificate: see SIGNING_INFO.txt\n"
        "Build checksum: see SHA256SUMS.txt\n"
        "Phase06 nested archives audited: " + str(counts["audited_containers"]) + "\n"
        "Phase06 nested archive members: " + str(counts["inspected_entries"]) + "\n"
        "Phase06 small textual payloads scanned: " + str(counts["scanned_text_files"]) + "\n"
        "Phase06 ZIP/TAR nesting and credential signature gate: PASSED\n"
        "Large binaries, runtime memory and unknown encrypted/obfuscated secrets are not audited.\n"
        "Repository visibility must be verified separately in GitHub settings.\n",
        encoding="utf-8",
    )
    print("APK packaging audit passed; bundled Python bytecode is not protected.")
    return output


def main(args):
    if args == ["preflight"]:
        check_configuration()
        check_files()
        print("Android security source/configuration preflight passed.")
    elif len(args) == 2 and args[0] == "report":
        report(args[1])
    else:
        raise SystemExit(
            "Usage: python tools/android_hardening.py preflight | report APK")


if __name__ == "__main__":
    main(sys.argv[1:])
