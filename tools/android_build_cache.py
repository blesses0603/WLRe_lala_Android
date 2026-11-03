"""Version-aware key for the non-secret Android SDK/NDK/Gradle download cache.

Only restored dependencies may be cached. Do not add staged APKs, p4a
compiled outputs, key stores, application private files or source trees.
"""
from __future__ import annotations

import configparser
import hashlib
from importlib.metadata import version as installed_version
import json
import os
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = 1

# App version deliberately excluded: a Patch-only code change does not
# change the Android SDK/NDK/Gradle download requirements.
TOOLCHAIN_FIELDS = (
    "android.api", "android.minapi", "android.archs",
    "android.ndk", "android.ndk_api", "p4a.branch", "p4a.commit",
    "requirements",
)


def cache_key(spec_path=ROOT / "buildozer.spec", *, tool_versions=None):
    """Fingerprint exact toolchain dependencies without user data or secrets."""
    config = configparser.ConfigParser(interpolation=None)
    if not config.read(spec_path, encoding="utf-8"):
        raise ValueError("Android Buildozer configuration missing")
    if not config.has_section("app"):
        raise ValueError("Buildozer app configuration missing")
    values = {field: config.get("app", field, fallback="").strip()
              for field in TOOLCHAIN_FIELDS}
    if (not re.fullmatch(r"[a-f0-9]{40}", values["p4a.commit"])
            or not values["requirements"]
            or not values["android.api"]
            or values["android.archs"] != "arm64-v8a"):
        raise ValueError("Android pinned build inputs missing or unsupported")
    if tool_versions is None:
        tool_versions = {
            "buildozer": installed_version("buildozer"),
            "Cython": installed_version("Cython"),
        }
    if set(tool_versions) != {"buildozer", "Cython"}:
        raise ValueError("Unsupported Android cache tool versions")
    inputs = {
        "schema": SCHEMA,
        "runner": "ubuntu-22.04",
        "python": "3.11",
        "java": "17",
        "tool_versions": {k: str(v) for k, v in sorted(tool_versions.items())},
        "spec_fields": values,
    }
    body = json.dumps(inputs, ensure_ascii=True, sort_keys=True,
                      separators=(",", ":")).encode("ascii")
    return hashlib.sha256(body).hexdigest()[:32]


def main():
    digest = cache_key()
    output = os.environ.get("GITHUB_OUTPUT")
    if not output:
        raise RuntimeError("GITHUB_OUTPUT is required for workflow cache key")
    with open(output, "a", encoding="utf-8") as stream:
        stream.write("key=" + digest + "\n")
    print("Android non-secret dependency cache fingerprint prepared")


if __name__ == "__main__":
    main()
