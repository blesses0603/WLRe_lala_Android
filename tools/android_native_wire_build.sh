#!/usr/bin/env bash
# EXPERIMENTAL: Build isolated native-wire ARM64 APK without GitHub Actions.
# This output is NOT a persistent-signed release; do not install as an update.
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: ANDROID_PYC_PYTHON=/path/to/p4a-hostpython3.14 $0 /absolute/outside-repo/stage" >&2
  exit 2
fi
if [[ "$1" != /* ]]; then
  echo "Stage destination must be an absolute path outside the Git repository" >&2
  exit 2
fi
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAGE="$1"
PYTHON="${PYTHON:-python3}"
for tool in "$PYTHON" buildozer file; do
  command -v "$tool" >/dev/null || { echo "Missing tool: $tool" >&2; exit 2; }
done
if [[ -z "${ANDROID_PYC_PYTHON:-}" ]]; then
  echo "Set ANDROID_PYC_PYTHON to the matching p4a hostpython (target Python 3.14.2)." >&2
  exit 2
fi
if ! command -v "$ANDROID_PYC_PYTHON" >/dev/null && [[ ! -x "$ANDROID_PYC_PYTHON" ]]; then
  echo "Missing target-compatible hostpython: $ANDROID_PYC_PYTHON" >&2
  exit 2
fi
echo "== Phase04: validate host Python vectors (not ARM64 proof) =="
(cd "$ROOT" && "$PYTHON" -m unittest tests.test_android_cython_wire tests.test_android_native_wire -q)
echo "== Phase04: stage native-wire Android source in $STAGE =="
"$PYTHON" "$ROOT/tools/android_native_wire.py" stage --source "$ROOT" --output "$STAGE"
echo "== Phase04: compile with Buildozer, pinned p4a and Android NDK =="
(cd "$STAGE" && buildozer -v android debug)
mapfile -t APK_FILES < <(find "$STAGE/bin" -maxdepth 1 -type f -name '*.apk' | sort)
if [[ ${#APK_FILES[@]} -ne 1 ]]; then
  echo "Expected exactly one experimental APK; found ${#APK_FILES[@]}" >&2
  exit 1
fi
APK="${APK_FILES[0]}"
echo "== Phase04: ELF, bytecode and native-shim inspection =="
"$PYTHON" "$ROOT/tools/android_native_wire.py" verify-apk "$APK" --pyc-python "$ANDROID_PYC_PYTHON"
"$PYTHON" "$ROOT/tools/android_hardening.py" report "$APK"
"$PYTHON" "$ROOT/tools/android_presplash.py" check-apk "$APK"
sha256sum "$APK" | tee "$STAGE/EXPERIMENTAL_ARM64_SHA256SUMS.txt"
echo "Native build completed: $APK"
echo "EXPERIMENT ONLY: not authorized for pinned-signature upgrades."
