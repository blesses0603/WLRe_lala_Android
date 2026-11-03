#!/usr/bin/env python3
"""Run Android unittest files in separate processes to locate abrupt exits."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

TESTS = Path("tests")
TIMEOUT_SECONDS = 90


def main() -> int:
    files = sorted(TESTS.glob("test*.py"))
    if not files:
        print("ERROR: No test files discovered in tests/", flush=True)
        return 1

    failures = []
    print(f"Isolated Android regression: {len(files)} test files", flush=True)
    for index, path in enumerate(files, 1):
        print(f"\n=== [{index}/{len(files)}] START {path} ===", flush=True)
        command = [
            "xvfb-run", "-a", sys.executable, "-u", "-m", "unittest",
            "discover", "-s", str(TESTS), "-p", path.name, "-v",
        ]
        try:
            result = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                errors="replace",
                timeout=TIMEOUT_SECONDS,
                env={**os.environ, "PYTHONUNBUFFERED": "1"},
                check=False,
            )
            output = result.stdout
            code = result.returncode
        except subprocess.TimeoutExpired as exc:
            output = exc.stdout or b""
            if isinstance(output, bytes):
                output = output.decode("utf-8", errors="replace")
            code = 124
            output += f"\nTIMEOUT after {TIMEOUT_SECONDS} seconds\n"

        if output:
            print(output, end="" if output.endswith("\n") else "\n", flush=True)
        print(f"=== END {path}: exit={code} ===", flush=True)
        if code != 0:
            failures.append((str(path), code))

    print(f"\nSUMMARY: {len(files) - len(failures)} passed, {len(failures)} failed", flush=True)
    for path, code in failures:
        print(f"FAILED {path}: exit={code}", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
