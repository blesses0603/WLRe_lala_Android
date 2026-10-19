"""Phase09 fail-closed Android APK release identity and evidence manifest.

This final offline verifier runs AFTER fixed signing, all native/security audits,
and the APK checksum, but BEFORE upload. It does not handle signing secrets.
Its JSON manifest is a reproducible evidence index, NOT cryptographic signing
or independently verified supply-chain attestation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import zipfile

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.android_release_version import source_version
from tools.android_signing import _fingerprint

PACKAGE = "org.lala.client.wlrelala"
REQUIRED_REPORTS = {
    "NATIVE_WIRE_INFO.txt": (
        "Native wire Cython extension: VERIFIED",
        "Original wire implementation source/bytecode leaks: 0",
    ),
    "NATIVE_VAULT_INFO.txt": (
        "ARM64 Cython extension VERIFIED",
        "Original vault Python implementation source/bytecode leaks: 0",
    ),
    "PHASE05_ALL_CORES_INFO.txt": (
        "Previously native wire and vault: VERIFIED",
        "Python implementations of these six cores exposed: 0",
    ),
    "PRESPLASH_INFO.txt": ("Bundled icon comparison: PASSED",),
    "SIGNING_INFO.txt": (
        "Mode: persistent",
        "Pinned public signer SHA256: VERIFIED",
    ),
    "RUNTIME_INTEGRITY_INFO.txt": (
        "Staged Java package and public signer certificate pin: VERIFIED",
        "Compiled APK DEX contains runtime signer pin: VERIFIED",
    ),
    "PROTECTION_INFO.txt": (
        "Phase 03 application .py source leakage gate: PASSED",
        "Phase06 ZIP/TAR nesting and credential signature gate: PASSED",
    ),
}
APK_HASHES = "SHA256SUMS.txt"
EVIDENCE = "RELEASE_EVIDENCE.json"
EVIDENCE_HASHES = "REPORT_SHA256SUMS.txt"
APK_BASENAME = re.compile(r"WLRe_LaLa-Android-v[0-9]+\.[0-9]+\.[0-9]+-debug\.apk\Z")
CERT_LINE = re.compile(r"(?m)^Certificate SHA256: ([A-Fa-f0-9: ]+)$")
AAPT_PACKAGE = re.compile(
    r"^package:\s+name='([^']+)'\s+versionCode='([0-9]+)'\s+versionName='([^']+)'"
)
AAPT_SDK = re.compile(r"^sdkVersion:'([0-9]+)'$")
AAPT_TARGET = re.compile(r"^targetSdkVersion:'([0-9]+)'$")
HEX40 = re.compile(r"[0-9a-f]{40}\Z")


def _digest(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _locate_aapt():
    explicit = os.environ.get("ANDROID_AAPT")
    if explicit:
        return explicit
    root = Path.home() / ".buildozer/android/platform/android-sdk/build-tools"
    available = sorted(root.glob("*/aapt"))
    if available:
        return str(available[-1])
    return shutil.which("aapt")


def _apk_metadata(apk, *, aapt=None):
    executable = aapt if aapt is not None else _locate_aapt()
    if not executable:
        raise ValueError("Android SDK aapt required to verify final package metadata")
    result = subprocess.run(
        [str(executable), "dump", "badging", str(apk)],
        check=True, capture_output=True, text=True, timeout=30,
    )
    parsed = {}
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith("package:"):
            match = AAPT_PACKAGE.match(stripped)
            if not match:
                raise ValueError("Unparseable Android package identity")
            parsed["package"], parsed["version_code"], parsed["version_name"] = match.groups()
        elif stripped.startswith("sdkVersion:"):
            match = AAPT_SDK.fullmatch(stripped)
            if match:
                parsed["min_sdk"] = int(match.group(1))
        elif stripped.startswith("targetSdkVersion:"):
            match = AAPT_TARGET.fullmatch(stripped)
            if match:
                parsed["target_sdk"] = int(match.group(1))
    if set(parsed) != {"package", "version_code", "version_name", "min_sdk", "target_sdk"}:
        raise ValueError("Android APK package/version/API information missing")
    return parsed


def verify_release(output_dir, *, expected_version, source_root, source_sha,
                   git_ref, event, expected_signer, aapt=None):
    """Verify required evidence and return non-secret structured release metadata."""
    version = source_version(
        Path(source_root) / "buildozer.spec",
        Path(source_root) / "android_app/version.py",
    )
    if version != expected_version:
        raise ValueError("Phase09 release version does not match source")
    if not HEX40.fullmatch(source_sha):
        raise ValueError("Phase09 release source SHA invalid")
    if event == "workflow_dispatch":
        if git_ref != "refs/heads/main":
            raise ValueError("Manual signed Android build must originate from main")
    elif event == "push":
        if git_ref != "refs/tags/" + version:
            raise ValueError("Android signed release tag does not match version")
    else:
        raise ValueError("Unsupported Android signed release event")

    root = Path(output_dir).resolve(strict=True)
    expected_name = "WLRe_LaLa-Android-" + version + "-debug.apk"
    allowed = set(REQUIRED_REPORTS) | {
        expected_name, APK_HASHES
    }
    entries = list(root.iterdir())
    if (len(entries) != len(allowed) or
            {p.name for p in entries} != allowed or
            any(p.is_symlink() or not p.is_file() for p in entries)):
        raise ValueError("Incomplete or unexpected Phase09 Android output files")
    apk = root / expected_name
    if not APK_BASENAME.fullmatch(apk.name):
        raise ValueError("Malformed Android APK artifact filename")
    if not zipfile.is_zipfile(apk):
        raise ValueError("Release candidate is not a valid APK ZIP")
    actual_checksum = _digest(apk)
    expected_hash_line = f"{actual_checksum}  {apk.name}\n"
    if (root / APK_HASHES).read_text(encoding="ascii") != expected_hash_line:
        raise ValueError("APK SHA256SUMS does not match final signed APK")

    reports = {}
    for name, markers in REQUIRED_REPORTS.items():
        path = root / name
        if not 30 <= path.stat().st_size <= 128 * 1024:
            raise ValueError("Phase09 required report missing or oversized")
        data = path.read_text(encoding="utf-8")
        if any(marker not in data for marker in markers):
            raise ValueError("Required security report has not passed")
        reports[name] = {"sha256": _digest(path), "size_bytes": path.stat().st_size}

    signing = (root / "SIGNING_INFO.txt").read_text(encoding="utf-8")
    cert = CERT_LINE.search(signing)
    if not cert:
        raise ValueError("Missing APK signer certificate in signing report")
    if _fingerprint(cert.group(1)) != _fingerprint(expected_signer):
        raise ValueError("Signed APK evidence does not match expected public certificate")
    metadata = _apk_metadata(apk, aapt=aapt)
    if metadata["package"] != PACKAGE or metadata["version_name"] != version[1:]:
        raise ValueError("Android APK package/versionName identity mismatch")
    if int(metadata["version_code"]) <= 0:
        raise ValueError("Android APK versionCode must be positive")
    if metadata["min_sdk"] != 31 or metadata["target_sdk"] != 35:
        raise ValueError("Unexpected Android APK SDK compatibility")
    # No guessed ABI: app native ELF inventories were checked earlier by
    # native wire/vault/cores verifiers and Phase03/06 archive auditor.

    return {
        "schema_version": 1,
        "project": "WLRe_LaLa_Android",
        "apk": {
            "filename": apk.name,
            "sha256": actual_checksum,
            "size_bytes": apk.stat().st_size,
            "package": metadata["package"],
            "version_name": metadata["version_name"],
            "version_code": int(metadata["version_code"]),
            "min_sdk": metadata["min_sdk"],
            "target_sdk": metadata["target_sdk"],
            "abi": "arm64-v8a",
        },
        "source": {"commit_sha": source_sha, "git_ref": git_ref, "event": event},
        "public_certificate_sha256": _fingerprint(expected_signer),
        "reports": reports,
        "apk_sha256sums_sha256": _digest(root / APK_HASHES),
        "limits": {
            "signing_mode": "persistent-debug-test-key",
            "android_real_device_test": "not_claimed",
            "binary_reproducibility": "not_claimed",
            "independent_attestation": "not_claimed",
        },
    }


def finalize_release(output_dir, *, expected_version, source_root, source_sha,
                     git_ref, event, expected_signer, aapt=None):
    root = Path(output_dir).resolve(strict=True)
    for pending in (EVIDENCE, EVIDENCE_HASHES):
        if (root / pending).exists() or (root / pending).is_symlink():
            raise ValueError("Phase09 output already finalized; use a new empty directory")
    result = verify_release(
        root, expected_version=expected_version, source_root=source_root,
        source_sha=source_sha, git_ref=git_ref, event=event,
        expected_signer=expected_signer, aapt=aapt,
    )
    manifest = root / EVIDENCE
    checksums = root / EVIDENCE_HASHES
    manifest.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    names = sorted(set(REQUIRED_REPORTS) | {APK_HASHES, EVIDENCE})
    checksums.write_text(
        "".join(f"{_digest(root / filename)}  {filename}\n" for filename in names),
        encoding="ascii",
    )
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--source-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--sha", required=True)
    parser.add_argument("--ref", required=True)
    parser.add_argument("--event", required=True)
    parser.add_argument("--signer", required=True)
    opts = parser.parse_args(argv)
    path = finalize_release(
        opts.output_dir, expected_version=opts.version,
        source_root=opts.source_root, source_sha=opts.sha,
        git_ref=opts.ref, event=opts.event, expected_signer=opts.signer,
    )
    print("Phase09 final APK identity, required security reports and SHA256: VERIFIED")
    print("Android release evidence manifest created:", path.name)


if __name__ == "__main__":
    main()
