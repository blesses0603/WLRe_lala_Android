# Android / Desktop parity checkpoint (2026-10-20)

## Baselines and truthfulness

Desktop: `blesses0603/WLRe_lala/main` at `403679657d15b2ff79f8df44f8c510805e367bd8`.
Android: `blesses0603/WLRe_lala_Android/main` at `533fe07a6d22f69f664d8a2ceca4d15232e87bb3` (Android v0.0.8).

**This UI PR is not a full desktop feature port.** Avoid asserting a feature exists just
because a similarly named menu or bundled desktop file exists. Android remains an
independent, ARM64-only platform with protected native P0/P1 cores and limited IPC.

## Implemented in this PR

- Native bootstrap splash: generate 512px dark canvas and a centered 196px logo,
  without enlarging the actual launcher icon or changing signatures.
- Crafting catalog: stable 88dp cards, six recipes per page, separate name, state,
  icon, and details action; group production queue below the catalog.
- Dashboard: compact selector, preserve existing 13 working feature pages.
- Overlay: online game character becomes the heading; no masked or raw login account,
  and no duplicate name block. Event status is followed by divider and actual EXP/h
  total, last-10 and last-30 summaries, with honest empty-sample placeholders.

## Desktop differences requiring separate, gated engineering

| Desktop main module / capability | Android current status | Safe next step |
| --- | --- | --- |
| `network/instances.py`, `instance_actions.py` and `services/instance_*.py` | **Not ported** | Port read-only snapshot parsing first; validate confirmed server responses and IDs |
| 副本／協力建立房間、加入、準備、開始、獎勵 | **Not available on Android** | Explicit IPC allowlist, confirmations, no blind retry; mobile room window and 720p regression |
| `services/battle/attribute_points.py` | **Not ported** | Examine attribute state schema, add read-only mobile display, then guarded allocations |
| `network/commands.py`, `command_envelope.py`, `service_scheduler.py` | Android service architecture differs | Compare semantics; port only verified changes with native-core tests |
| `core/state_*_events.py`, `services/coordination.py` | Android uses earlier monolithic state/network path | Port incrementally with state/event regression and protocol fixtures |
| Desktop refactored expedition manager and crafting reservations | Android has earlier functional logic | Behavioral diff and regression tests before any protected-core replacement |

Current Android features documented in `ANDROID/FEATURE_PARITY.md` still exist:
battle, roaming, bag, room storage (read-only), map, party, companions, expeditions,
alchemy, crafting, chat, EXP and event history. These are not all at identical
desktop revisions. Cross-platform Python modules with the same path but different
Git SHA do not by themselves prove functional incompatibility.

## Release and safety gates

- PR checks: `android-smoke.yml` only (unit/UI tests, Python syntax, hardening).
- New signed ARM64 APK is **not** produced by an ordinary PR; native build remains
  manual on `main` or a validated release tag.
- Do not merge desktop native Python code into Android P0/P1 shim files; follow
  Phase05 stage + audit + signing verification for future core ports.
- Real phone acceptance still needed: normal cold start, 1-hand portrait layout,
  scroll/pagination in crafting, multi-account overlay, EXP sample progression,
  rotation/IME, app pause/resume and lock-screen service continuity.
