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
NATIVE_CACHE_SCHEMA = 1

# The compiled p4a cache deliberately stops BEFORE LaLa's own native recipes
# and excludes all application distributions, private sources and APKs.
# These are exact p4a "other_builds" folder names, not glob patterns.
P4A_THIRD_PARTY_FOLDERS = (
    "freetype", "hostpython3", "jpeg", "libffi", "liblzma",
    "libwebp", "openssl", "png", "sqlite3", "python3-liblzma",
)
P4A_THIRD_PARTY_PACKAGE_FOLDERS = (
    "freetype", "hostpython3", "jpeg", "libffi", "liblzma",
    "libwebp", "openssl", "png", "sqlite3", "python3",
)

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



def native_cache_key(spec_path=ROOT / "buildozer.spec", *,
                     recipes_root=ROOT / "p4a-recipes",
                     image_version=None, tool_versions=None):
    """Fingerprint native dependencies independently from application sources.

    A new runner image must never reuse precompiled host/target objects from
    another image. Unidentified runner images disable the compiled cache.
    Local p4a recipe overrides are included, even though only vetted built-in
    recipes are restored.
    """
    image = os.environ.get("ImageVersion") if image_version is None else image_version
    if not image or not re.fullmatch(r"[A-Za-z0-9_.-]{2,128}", image):
        return None
    root = Path(recipes_root)
    if not root.is_dir() or root.is_symlink():
        raise ValueError("Local p4a recipes missing or unsafe")
    digest = hashlib.sha256()
    source_files = sorted(
        path for path in root.rglob("*")
        if path.is_file() and path.suffix.lower()
        in {".py", ".patch", ".diff", ".sh", ".txt", ".toml", ".cfg", ".json"}
    )
    if not source_files:
        raise ValueError("Local p4a recipe definitions missing")
    for path in source_files:
        if path.is_symlink() or path.stat().st_size > 2 * 1024 * 1024:
            raise ValueError("Untrusted p4a recipe input")
        digest.update(path.relative_to(root).as_posix().encode("utf-8") + b"\\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    inputs = {
        "schema": NATIVE_CACHE_SCHEMA,
        "platform_key": cache_key(spec_path, tool_versions=tool_versions),
        "runner_image": image,
        "local_recipes_sha256": digest.hexdigest(),
        "allowlisted_other_builds": P4A_THIRD_PARTY_FOLDERS,
        "allowlisted_packages": P4A_THIRD_PARTY_PACKAGE_FOLDERS,
        "ndk_revision": "r28c",
        "ndk_target_api": "31",
        "arch": "arm64-v8a",
    }
    body = json.dumps(inputs, sort_keys=True, separators=(",", ":")).encode("ascii")
    return hashlib.sha256(body).hexdigest()[:32]


def safe_third_party_paths():
    """The only paths allowed in the separate compiled-recipe cache."""
    root = ".buildozer/android/platform/build-arm64-v8a"
    return (
        tuple(root + "/build/other_builds/" + folder
              for folder in P4A_THIRD_PARTY_FOLDERS)
        + tuple(root + "/packages/" + folder
                for folder in P4A_THIRD_PARTY_PACKAGE_FOLDERS)
    )


def main():
    digest = cache_key()
    output = os.environ.get("GITHUB_OUTPUT")
    if not output:
        raise RuntimeError("GITHUB_OUTPUT is required for workflow cache key")
    with open(output, "a", encoding="utf-8") as stream:
        stream.write("key=" + digest + "\n")
    compiled = native_cache_key()
    with open(output, "a", encoding="utf-8") as stream:
        stream.write("native_key=" + (compiled or "disabled") + "\\n")
        stream.write("native_enabled=" + ("true" if compiled else "false") + "\\n")
    print("Android non-secret dependency cache fingerprint prepared")
    if compiled:
        print("Version-locked p4a third-party build cache enabled")
    else:
        print("No trusted runner ImageVersion; p4a compiled cache disabled")


if __name__ == "__main__":
    main()
