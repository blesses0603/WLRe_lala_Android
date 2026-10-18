"""Shared Android debug signing for Smoke ARM64/x86_64 and tagged builds.

GitHub Actions workers are disposable. A repository secret must contain the
SAME base64-encoded Android debug keystore for signatures to stay consistent.
Never upload, print, or commit the private keystore.
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
ENV_MODE = "ANDROID_SIGNING_MODE"
KEYSTORE = Path.home() / ".android" / "debug.keystore"
ALIAS = "androiddebugkey"
PASSWORD = "android"


def _set_mode(mode):
    output = os.environ.get("GITHUB_ENV")
    if output:
        with open(output, "a", encoding="utf-8") as stream:
            stream.write(ENV_MODE + "=" + mode + "\n")


def prepare(encoded=None, keystore=None):
    """Install a persistent debug key; never silently fall back on a bad secret."""
    if encoded is None:
        encoded = os.environ.get(ENV_SECRET, "")
    if keystore is None:
        keystore = KEYSTORE
    keystore = Path(keystore)
    if not encoded:
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
        subprocess.run([
            "keytool", "-list", "-keystore", temp, "-storepass", PASSWORD,
            "-alias", ALIAS,
        ], check=True, capture_output=True, text=True, timeout=30)
        os.replace(temp, keystore)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    _set_mode("persistent")
    print("Persistent Android debug signing key restored (private key redacted).")
    return True


def signing_info(output_dir, keystore=None, apksigner=None):
    """Provide a public certificate fingerprint and signing mode with each APK."""
    if keystore is None:
        keystore = KEYSTORE
    command = [
        "keytool", "-list", "-v", "-keystore", str(keystore),
        "-storepass", PASSWORD, "-alias", ALIAS,
    ]
    result = subprocess.run(command, capture_output=True, text=True,
                            check=True, timeout=30)
    match = re.search(r"SHA256:\s*([0-9A-Fa-f:]+)", result.stdout)
    if match is None:
        raise ValueError("Could not read Android signing certificate fingerprint")
    # Verify the built APK itself, not merely that a keystore file exists.
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
    actual = re.search(r"certificate SHA-256 digest:\s*([0-9A-Fa-f]+)", verified.stdout)
    if actual is None or actual.group(1).lower() != match.group(1).replace(":", "").lower():
        raise ValueError("APK certificate does not match configured debug keystore")
    mode = os.environ.get(ENV_MODE, "ephemeral")
    lines = [
        "Android debug APK signing (public certificate identity)",
        "Mode: " + mode,
        "Certificate SHA256: " + match.group(1).upper(),
        "APK signer certificate verified against the debug keystore.",
        "The certificate SHA256 above is NOT the APK file checksum.",
        "Identical certificates require the same persistent private keystore.",
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
