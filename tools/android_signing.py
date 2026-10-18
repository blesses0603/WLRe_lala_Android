"""Shared ARM64 Android signing checks for PR and downloadable APKs.

A private GitHub Secret restores the same keystore across separate workers.
A separately pinned *public* SHA-256 certificate fingerprint detects rotation.
No keystore material, environment secrets, or keytool output is logged.
"""
import base64
import binascii
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


ENV_SECRET = "ANDROID_DEBUG_KEYSTORE_BASE64"
ENV_PIN = "ANDROID_EXPECTED_SIGNER_SHA256"
ENV_MODE = "ANDROID_SIGNING_MODE"
KEYSTORE = Path.home() / ".android" / "debug.keystore"
ALIAS = "androiddebugkey"
PASSWORD = "android"


def _set_mode(mode):
    output = os.environ.get("GITHUB_ENV")
    if output:
        with open(output, "a", encoding="utf-8") as stream:
            stream.write(ENV_MODE + "=" + mode + "\n")


def _fingerprint(value):
    """Normalize a public certificate SHA-256, rejecting incomplete fingerprints."""
    compact = value.replace(":", "").replace(" ", "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", compact):
        raise ValueError("Expected a complete 32-byte SHA256 signer fingerprint")
    return compact


def _configured_pin(required=False):
    value = os.environ.get(ENV_PIN, "").strip()
    if not value:
        if required:
            raise RuntimeError(
                "Persistent signing needs ANDROID_EXPECTED_SIGNER_SHA256 GitHub "
                "Actions variable to pin the expected public certificate.")
        return None
    return _fingerprint(value)


def _keytool_fingerprint(stdout):
    match = re.search(r"\bSHA-?256:\s*([0-9A-Fa-f: ]+)", stdout, re.I)
    if match is None:
        raise ValueError("Keytool did not report certificate SHA256")
    return _fingerprint(match.group(1))


def prepare(encoded=None, keystore=None):
    """Restore only the pinned persistent signer; never fall back on a bad key."""
    if encoded is None:
        encoded = os.environ.get(ENV_SECRET, "")
    if keystore is None:
        keystore = KEYSTORE
    keystore = Path(keystore)
    require = os.environ.get("ANDROID_REQUIRE_PERSISTENT_SIGNING") == "1"
    pin = _configured_pin(required=require)
    if not encoded:
        if require:
            raise RuntimeError(
                "Persistent signing is mandatory for tagged/manual phone builds. "
                "Set ANDROID_DEBUG_KEYSTORE_BASE64 in GitHub Actions Secrets "
                "and keep the private keystore off GitHub.")
        print("::warning::ANDROID_DEBUG_KEYSTORE_BASE64 is not set. "
              "This run uses a temporary CI debug key; APK signatures "
              "will NOT match across runs. See ANDROID/SIGNING.md.")
        _set_mode("ephemeral")
        return False
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("Invalid base64 Android signing secret") from exc
    if not 128 <= len(raw) <= 8 * 1024 * 1024:
        raise ValueError("Android signing secret size is invalid")
    keystore.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".debug-keystore-", dir=keystore.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp, 0o600)
        # Fail this build if the persistent secret is invalid rather than
        # publishing another randomly signed APK.
        verified = subprocess.run([
            "keytool", "-list", "-v", "-keystore", temp, "-storepass", PASSWORD,
            "-alias", ALIAS,
        ], check=True, capture_output=True, text=True, timeout=30)
        actual = _keytool_fingerprint(verified.stdout)
        if pin and actual != pin:
            raise ValueError("Signing keystore certificate does not match pinned SHA256")
        os.replace(temp, keystore)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    _set_mode("persistent")
    print("Persistent Android debug signing key restored (private key redacted).")
    return True


def signing_info(output_dir, keystore=None, apksigner=None):
    """Verify the APK signature and publish its public signer fingerprint.

    An ephemeral Gradle key is often generated under a build distribution,
    not ~/.android/debug.keystore. Only persistent mode may assume our
    restored keystore is present; ephemeral mode reports the APK cert itself.
    """
    require = os.environ.get("ANDROID_REQUIRE_PERSISTENT_SIGNING") == "1"
    pin = _configured_pin(required=require)
    mode = os.environ.get(ENV_MODE, "ephemeral")
    if require and mode != "persistent":
        raise RuntimeError("Release build refused: persistent signing is required")
    candidates = list(Path(output_dir).glob("*.apk"))
    if len(candidates) != 1:
        raise ValueError("Expected exactly one built Android APK for signature verification")
    if apksigner is None:
        sdk_tools = Path.home() / ".buildozer/android/platform/android-sdk/build-tools"
        options = sorted(sdk_tools.glob("*/apksigner"))
        apksigner = str(options[-1]) if options else shutil.which("apksigner")
    if not apksigner:
        raise FileNotFoundError("Android SDK apksigner is required to validate the APK signature")

    verified = subprocess.run([str(apksigner), "verify", "--print-certs",
                               str(candidates[0])], capture_output=True, text=True,
                              check=True, timeout=30)
    fingerprints = re.findall(
        r"certificate SHA-256 digest:\s*([0-9A-Fa-f]+)", verified.stdout, re.I)
    if len(fingerprints) != 1:
        raise ValueError("Expected exactly one APK signer certificate")
    apk_fingerprint = _fingerprint(fingerprints[0])
    if pin and apk_fingerprint != pin:
        raise ValueError("APK certificate does not match pinned SHA256")

    if mode == "persistent":
        if keystore is None:
            keystore = KEYSTORE
        command = ["keytool", "-list", "-v", "-keystore", str(keystore),
                   "-storepass", PASSWORD, "-alias", ALIAS]
        result = subprocess.run(command, capture_output=True, text=True,
                                check=True, timeout=30)
        if _keytool_fingerprint(result.stdout) != apk_fingerprint:
            raise ValueError("APK certificate does not match configured debug keystore")
    elif mode != "ephemeral":
        raise ValueError("Unrecognized Android signing mode")

    # The actual APK certificate is authoritative; it is not a hash of the APK.
    fingerprint = ":".join(apk_fingerprint[i:i + 2] for i in range(
        0, len(apk_fingerprint), 2)).upper()
    lines = [
        "Android debug APK signing (public certificate identity)",
        "Mode: " + mode,
        "Certificate SHA256: " + fingerprint,
        "APK signature verified by Android SDK apksigner.",
        ("Pinned public signer SHA256: VERIFIED" if pin else
         "Pinned public signer SHA256: NOT CONFIGURED"),
        ("Signer also verified against the persistent debug keystore."
         if mode == "persistent" else
         "No persistent key configured; signature may change on another run."),
        "The certificate SHA256 above is NOT the APK file checksum.",
    ]
    dest = Path(output_dir) / "SIGNING_INFO.txt"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("APK signing mode: " + mode + "; certificate fingerprint recorded.")
    return str(dest)


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "prepare":
        prepare()
    elif len(sys.argv) == 3 and sys.argv[1] == "report":
        signing_info(sys.argv[2])
    else:
        raise SystemExit("Usage: android_signing.py prepare | report OUTPUT_DIR")
