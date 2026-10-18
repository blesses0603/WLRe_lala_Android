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
              "private_tar": False, "native_arm64_libraries": 0}
    def record(name):
        if _sensitive_filename(name):
            raise ValueError("APK contains a possible private credential file: " + name)
        lower = name.lower()
        if lower.endswith(".py"):
            counts["python_source"] += 1
        elif lower.endswith(".pyc") or lower.endswith(".pyo"):
            counts["python_bytecode"] += 1

    with zipfile.ZipFile(apk) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            record(info.filename)
            if info.filename.startswith("lib/arm64-v8a/") and info.filename.endswith(".so"):
                counts["native_arm64_libraries"] += 1
        if "assets/private.tar" in archive.namelist():
            counts["private_tar"] = True
            with archive.open("assets/private.tar") as payload:
                try:
                    # Streaming mode supports both plain TAR and gzip-compressed TAR.
                    with tarfile.open(fileobj=payload, mode="r|*") as members:
                        for member in members:
                            if member.isfile():
                                record(member.name)
                except (tarfile.TarError, EOFError, OSError) as exc:
                    raise ValueError("Unable to audit embedded assets/private.tar") from exc
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
        "ARM64 shared libraries (not proof of Cython): " +
            str(counts["native_arm64_libraries"]) + "\n"
        "Python bytecode can be extracted and analyzed; no obfuscation is claimed.\n"
        "Account vault at rest: Android Keystore with AES-GCM\n"
        "Build flavor: DEBUG test APK (NOT a store-ready release)\n"
        "Python code obfuscation/Cython: NOT enabled\n"
        "Anti-tamper runtime protection: NOT enabled\n"
        "APK signature certificate: see SIGNING_INFO.txt\n"
        "Build checksum: see SHA256SUMS.txt\n"
        "This audit inspects member names, not all secrets inside nested ZIPs or binaries.\n"
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
