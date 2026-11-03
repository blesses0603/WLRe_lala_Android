# Android ↔ Desktop v7.1.1: Eve/Convey portal core sync

Source: desktop `blesses0603/WLRe_lala` commit `7c31aa266f22bc79cb9cd279463c2ac1f1ee6397` (main, v7.1.1).

This is **source integration**, not Android APK, device, or official-server acceptance.

## Synced in this PR

- Added `wlre/services/world/event_portals.py`: match verified Eve doors to PlayerTouch → Convey effects without guessing event flags, target scenes, or gate requirements.
- Updated `doors_1275.py` to decode Convey sections, retain conditional branches, validate section offsets, and decode length-prefixed names.
- Updated `boundary_portals.py` and `bundle_runtime_1275.py` to integrate event-derived physical exit bindings; updated `preview_1275.py` so offline preview uses the same evidence.
- Updated `portals.py`, `portal_policy.py`, `portal_travel.py`, `portal_coverage.py`, and `portal_inspection_1275.py` for route display, destination candidates, same-scene movement, and unknown/conditional outcomes.
- Added desktop `tests/test_event_convey_portals.py` to Android regression suite, including actual door ID and multi-target/same-scene cases.
- Refreshed the SHA-256 source lock for these 10 modules. Kept the five reviewed Android adaptations (manifest parsing, Cython expedition imports, command validation, crafting status) unchanged.

## Explicit limits

- No hardcoded giant-whale-island coordinates or invented quest completion. The runtime decodes verified same-version official source records; the game server alone decides whether a gate is available and confirms the destination.
- The Android UI remains Kivy rather than the desktop Tkinter UI; no desktop-only launcher/UI modules are copied into the APK.
- Desktop `wlre/resource_manifest.py` has a changed list of desktop UI icon requirements; this is **not** copied without the corresponding Android asset packaging review.
- `ANDROID/DESKTOP_SOURCE_LOCK.json` retains `desktop_source` pinned to the prior reviewed seed commit because `tools/android_resource_seed.py` downloads the verified SQLite seed by that reference. The new `desktop_core_sync_ref` identifies the v7.1.1 portal core source separately.
- Android app version remains `0.1.1` pending device and APK acceptance. CI/PR checks do not demonstrate on-device startup or official-server door traversal.

## Acceptance gates

1. `python tools/android_parity_audit.py` validates the updated source file checksums.
2. Android Smoke CI: Python regression and security checks, including the new event-Convey test module.
3. PR diagnostics pass, with **no APK packaging** from a PR.
4. After review and merge, a manually triggered main APK build must pass before claiming APK compatibility.
5. Official server walkthrough and in-game location confirmation remain separate, not claimed by this PR.
