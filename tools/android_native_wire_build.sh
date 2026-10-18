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
for tool in "$PYTHON" buildozer; do
  command -v "$tool" >/dev/null || { echo "Missing tool: $tool" >&2; exit 2; }
done
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
# The p4a hostpython is normally created DURING this first build; do not
# require it before the NDK toolchain has run.
if [[ -z "${ANDROID_PYC_PYTHON:-}" ]]; then
  mapfile -t PYTHON_CANDIDATES < <(
    find "$STAGE/.buildozer" -type f \( -name 'python3.14' -o -name 'python3.14m' \) -perm /111 2>/dev/null | sort
  )
  if [[ ${#PYTHON_CANDIDATES[@]} -eq 1 ]]; then
    ANDROID_PYC_PYTHON="${PYTHON_CANDIDATES[0]}"
  else
    echo "Could not uniquely locate pinned p4a hostpython3.14; specify ANDROID_PYC_PYTHON." >&2
    echo "APK candidate was built but native bytecode verification remains INCOMPLETE: $APK" >&2
    exit 1
  fi
fi
if ! command -v "$ANDROID_PYC_PYTHON" >/dev/null && [[ ! -x "$ANDROID_PYC_PYTHON" ]]; then
  echo "Cannot run target-compatible hostpython: $ANDROID_PYC_PYTHON" >&2
  exit 1
fi
echo "== Phase04: ELF, bytecode and native-shim inspection =="
"$PYTHON" "$ROOT/tools/android_native_wire.py" verify-apk "$APK" --pyc-python "$ANDROID_PYC_PYTHON"
"$PYTHON" "$ROOT/tools/android_hardening.py" report "$APK"
"$PYTHON" "$ROOT/tools/android_presplash.py" check-apk "$APK"
sha256sum "$APK" | tee "$STAGE/EXPERIMENTAL_ARM64_SHA256SUMS.txt"
echo "Native build completed: $APK"
echo "EXPERIMENT ONLY: not authorized for pinned-signature upgrades."
