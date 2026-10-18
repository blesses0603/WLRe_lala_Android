"""Resolve and validate the version used for Android GitHub Actions APK artifacts.

A pushed vX.Y.Z tag must match both source version declarations and point to
a main-branch commit (the latter is checked separately by the workflow).
Manual builds are allowed only from main, using the same source version.
"""
from __future__ import annotations

import ast
import configparser
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION_PATTERN = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+\Z")


def read_python_version(path: Path) -> str:
    module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for statement in module.body:
        if isinstance(statement, ast.Assign):
            names = [target.id for target in statement.targets if isinstance(target, ast.Name)]
            if "ANDROID_VERSION" in names:
                value = ast.literal_eval(statement.value)
                if isinstance(value, str):
                    return value
    raise ValueError(f"Missing string ANDROID_VERSION in {path}")


def resolve_version(spec_path: Path, python_path: Path, ref: str, event: str) -> str:
    config = configparser.ConfigParser(interpolation=None)
    if not config.read(spec_path, encoding="utf-8"):
        raise ValueError(f"Could not read {spec_path}")
    spec_version = config.get("app", "version").strip()
    python_version = read_python_version(python_path)
    if spec_version != python_version:
        raise ValueError(
            f"Version mismatch: buildozer.spec={spec_version}, "
            f"android_app/version.py={python_version}"
        )
    if not VERSION_PATTERN.fullmatch(spec_version):
        raise ValueError(f"Expected numeric X.Y.Z version, got {spec_version!r}")
    tag = f"v{spec_version}"
    if event == "push":
        if ref != f"refs/tags/{tag}":
            raise ValueError(f"Git tag {ref!r} does not match Android version {tag}")
    elif event == "workflow_dispatch":
        if ref != "refs/heads/main":
            raise ValueError(f"Manual Android APK builds must use main, got {ref!r}")
    else:
        raise ValueError(f"Unsupported APK build event: {event!r}")
    return tag


def main() -> None:
    version = resolve_version(
        ROOT / "buildozer.spec",
        ROOT / "android_app/version.py",
        os.environ.get("GITHUB_REF", ""),
        os.environ.get("GITHUB_EVENT_NAME", ""),
    )
    print(f"Android APK release version: {version}")
    output = os.environ.get("GITHUB_OUTPUT")
    if not output:
        raise RuntimeError("GITHUB_OUTPUT is required in GitHub Actions")
    with open(output, "a", encoding="utf-8") as stream:
        stream.write(f"version={version}\n")


if __name__ == "__main__":
    main()
