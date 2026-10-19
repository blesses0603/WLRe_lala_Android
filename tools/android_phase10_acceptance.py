"""Phase10 offline Android release receipt and optional real-device preflight.

The receipt checks the FINAL GitHub Artifact (not source-level mock reports).
Device preflight is read-only and will NEVER install/uninstall, clear app data,
read private app files, print full logcat, or ask for/save a game password.
The remaining interactive account/background tests require a human acceptance
record. This is not a substitute for server-side attestation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import zipfile
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.android_release_gate import (
    APK_HASHES, EVIDENCE, EVIDENCE_HASHES, PACKAGE, REQUIRED_REPORTS,
)
from tools.android_signing import _fingerprint

SHA256 = re.compile(r"[0-9a-f]{64}\Z")
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
HEX_SUM_LINE = re.compile(r"([0-9a-f]{64})  ([A-Za-z0-9_.-]+)\Z")
APK_CERT = re.compile(r"certificate SHA-256 digest:\s*([0-9A-Fa-f]+)", re.I)
MAX_REPORT = 128 * 1024
MAX_MANIFEST = 128 * 1024
ALLOWED = set(REQUIRED_REPORTS) | {APK_HASHES, EVIDENCE, EVIDENCE_HASHES}


def _sha(path):
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for data in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(data)
    return value.hexdigest()


def _object_no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate evidence JSON key")
        result[key] = value
    return result


def _checksums(content: str):
    entries = {}
    for line in content.splitlines():
        match = HEX_SUM_LINE.fullmatch(line)
        if not match:
            raise ValueError("Invalid Phase10 checksum manifest syntax")
        digest, filename = match.groups()
        if filename in entries:
            raise ValueError("Duplicate file in Phase10 checksum manifest")
        entries[filename] = digest
    return entries


def _run(command, *, timeout=30):
    return subprocess.run(
        command, check=True, capture_output=True, text=True, timeout=timeout,
    ).stdout


def verify_artifact(folder: Path, *, apksigner: str | None = None,
                    expected_commit: str | None = None):
    """Check digest graph AND signed APK identity from downloaded Artifact.

    This does not pretend a local attacker could not forge unsigned report
    files; apksigner remains the independent cryptographic certificate check.
    """
    root = Path(folder).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Artifact must be an extracted directory")
    entries = list(root.iterdir())
    apk_files = [p for p in entries if p.name.endswith(".apk")]
    if len(apk_files) != 1:
        raise ValueError("Exactly one signed Android APK is required")
    apk = apk_files[0]
    if ({p.name for p in entries} != ALLOWED | {apk.name}
            or len(entries) != len(ALLOWED) + 1
            or any(p.is_symlink() or not p.is_file() for p in entries)):
        raise ValueError("Artifact is missing mandatory evidence or contains extra files")
    for p in entries:
        if p != apk and p.stat().st_size > MAX_REPORT:
            raise ValueError("Oversized or untrusted Android release report")
    document = json.loads(
        (root / EVIDENCE).read_text(encoding="utf-8"),
        object_pairs_hook=_object_no_duplicates,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Non-finite evidence value")),
    )
    if not isinstance(document, dict) or document.get("schema_version") != 1:
        raise ValueError("Unsupported Android release evidence schema")
    release = document.get("apk", {})
    provenance = document.get("source", {})
    if not isinstance(release, dict) or not isinstance(provenance, dict):
        raise ValueError("Invalid APK/source release evidence")
    if release.get("filename") != apk.name or release.get("package") != PACKAGE:
        raise ValueError("Artifact package identity differs from evidence")
    if not isinstance(release.get("version_code"), int) or release["version_code"] <= 0:
        raise ValueError("APK must have a positive Android versionCode")
    if (release.get("min_sdk") != 31 or release.get("target_sdk") != 35
            or release.get("abi") != "arm64-v8a"):
        raise ValueError("Unexpected Android APK device compatibility")
    if release.get("size_bytes") != apk.stat().st_size:
        raise ValueError("APK size changed since release validation")
    if not SHA256.fullmatch(release.get("sha256", "")):
        raise ValueError("Invalid SHA256 release metadata")
    if not SHA40.fullmatch(provenance.get("commit_sha", "")):
        raise ValueError("Missing verifiable source commit")
    if expected_commit is not None and provenance["commit_sha"] != expected_commit:
        raise ValueError("Artifact was not built from the expected main commit")
    if provenance.get("event") == "workflow_dispatch":
        if provenance.get("git_ref") != "refs/heads/main":
            raise ValueError("Artifact was not generated from main")
    elif provenance.get("event") == "push":
        if provenance.get("git_ref") != "refs/tags/v" + release.get("version_name", ""):
            raise ValueError("Signed release ref differs from the APK version")
    else:
        raise ValueError("Unsupported signed Android release event")
    if not isinstance(release.get("version_name"), str):
        raise ValueError("Invalid Android version name")
    if not apk.name.endswith("-" + "v" + release["version_name"] + "-debug.apk"):
        raise ValueError("Android APK filename/version mismatch")
    if not zipfile.is_zipfile(apk) or _sha(apk) != release["sha256"]:
        raise ValueError("APK bytes differ from signed release evidence")
    if _checksums((root / APK_HASHES).read_text(encoding="ascii")) != {
        apk.name: release["sha256"]
    }:
        raise ValueError("APK SHA256SUMS does not match the final signed file")
    if _sha(root / APK_HASHES) != document.get("apk_sha256sums_sha256"):
        raise ValueError("SHA256SUMS digest differs from release evidence")

    report_evidence = document.get("reports")
    if (not isinstance(report_evidence, dict) or
            set(report_evidence) != set(REQUIRED_REPORTS)):
        raise ValueError("Incomplete Android security report evidence")
    checksum_evidence = _checksums(
        (root / EVIDENCE_HASHES).read_text(encoding="ascii"))
    expected_report_entries = set(REQUIRED_REPORTS) | {APK_HASHES, EVIDENCE}
    if set(checksum_evidence) != expected_report_entries:
        raise ValueError("Incomplete Phase10 report checksum list")
    for name in sorted(expected_report_entries):
        actual = _sha(root / name)
        if checksum_evidence[name] != actual:
            raise ValueError("Report checksum changed: " + name)
        if name in REQUIRED_REPORTS:
            info = report_evidence[name]
            if (not isinstance(info, dict) or info.get("sha256") != actual
                    or info.get("size_bytes") != (root / name).stat().st_size):
                raise ValueError("Security report metadata mismatch: " + name)
            text = (root / name).read_text(encoding="utf-8")
            if any(marker not in text for marker in REQUIRED_REPORTS[name]):
                raise ValueError("Security report no longer shows its required checks")

    signer = document.get("public_certificate_sha256", "")
    signer = _fingerprint(signer)
    signing_report = (root / "SIGNING_INFO.txt").read_text(encoding="utf-8")
    match = re.search(r"(?m)^Certificate SHA256:\s*([0-9A-Fa-f: ]+)$", signing_report)
    if (not match or _fingerprint(match.group(1)) != signer
            or "Mode: persistent" not in signing_report):
        raise ValueError("APK signer does not match persistent release evidence")
    sign_tool = apksigner or shutil.which("apksigner")
    if not sign_tool:
        raise ValueError("Android SDK apksigner required for real APK signature validation")
    output = _run([str(sign_tool), "verify", "--print-certs", str(apk)])
    certs = APK_CERT.findall(output)
    if len(certs) != 1 or _fingerprint(certs[0]) != signer:
        raise ValueError("Actual signed APK certificate does not match evidence")
    return {
        "artifact": "verified",
        "signed_apk": "verified",
        "release_commit": provenance["commit_sha"],
        "version": release["version_name"],
        "version_code": release["version_code"],
        "min_sdk": release["min_sdk"],
        "target_sdk": release["target_sdk"],
        "abi": release["abi"],
        "reports": len(REQUIRED_REPORTS),
        "physical_device_acceptance": "not_performed",
    }


def device_preflight(serial: str):
    """Read-only ADB check: enforce *physical* ARM64 phone, API 31 or higher."""
    if not serial or not re.fullmatch(r"[A-Za-z0-9._:-]{1,100}", serial):
        raise ValueError("A specific ADB serial is required")
    prefix = ["adb", "-s", serial, "shell"]
    sdk = _run(prefix + ["getprop", "ro.build.version.sdk"]).strip()
    abi = _run(prefix + ["getprop", "ro.product.cpu.abilist"]).strip()
    emulator = _run(prefix + ["getprop", "ro.kernel.qemu"]).strip()
    if not sdk.isdecimal() or int(sdk) < 31:
        raise ValueError("Device must run Android 12 (API 31) or newer")
    if "arm64-v8a" not in [value.strip() for value in abi.split(",")]:
        raise ValueError("A real ARM64-v8a device is required")
    if emulator == "1":
        raise ValueError("Android emulator results are not physical device acceptance")
    # No serial, model, account, path, keystore or logcat is written to output.
    return {
        "physical_device": "platform_signals_passed",
        "android_sdk": int(sdk),
        "arm64": True,
        "installed_app_test": "not_performed",
        "login_and_keystore_test": "not_performed",
        "background_15_30_60_minutes": "not_performed",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="action", required=True)
    v = modes.add_parser("verify-artifact")
    v.add_argument("folder", type=Path)
    v.add_argument("--apksigner")
    v.add_argument("--expected-commit")
    d = modes.add_parser("device-preflight")
    d.add_argument("--serial", required=True)
    opt = parser.parse_args(argv)
    if opt.action == "verify-artifact":
        value = verify_artifact(
            opt.folder, apksigner=opt.apksigner,
            expected_commit=opt.expected_commit)
    else:
        value = device_preflight(opt.serial)
    print(json.dumps(value, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
