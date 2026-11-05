# ItemData 1296 compatibility candidate

This is an Android source fix, not an APK or device acceptance result. It is
based on desktop commit `09f6707d449708dbc09e6ead8351c633e6e22191`, reviewed
against Android main `24a0d030288c2aa1d17b23aca28c01f237bb0193`.

## Accepted bytes and version

- Exact DataPackage version: `1296_2026_11_04_13_34_19_13`.
- Exact ItemData_C TextAsset SHA-256:
  `5195d5ee8ae201dea55439274914930551176c3fcf50d735e03b09c5d04acbb4`.
- Each record has two additional bytes after the legacy fields. The parser
  preserves them losslessly as `unknown_tail_1296_hex`, in original byte order.
  Their meaning is unknown and they do not authorize effects or transactions.
- Runtime, item adapter and shop enrichment pass their verified DataPackage
  version. Unknown versions, conflicting legacy versions and changed 1296
  payloads fail closed. No retry guesses a record size.
- Existing reviewed 1262, 1275 and 1286 full versions retain the legacy layout.
  Raw-only database/candidate readers recognize 1296 only by the exact digest;
  they do not independently authorize runtime activation.
- Complete record consumption, unique IDs, Unicode and size checks remain.
  SQLite retains original payloads and JSON-safe opaque metadata. Existing
  Manifest/Bundle integrity, cross-table checks, login gates and purchase
  restrictions remain unchanged.

An Android bundle is supported only if its extracted payload matches the
reviewed digest. A platform name or revision prefix is not proof of equality.

## Host validation

Focused parser, adapter, shop, database and runtime tests: 81 run, 80 passed,
1 skipped (private official bundle not supplied). Expanded catalog, resource
pipeline and Android safety tests: 124 run, 121 passed, 3 skipped (Kivy/display
login-gate checks). The wider non-Android host suite ran 800 tests: 798 passed
and 2 skipped (private bundle and Windows DPAPI). These groups overlap and
are not additive. Python syntax,
162-file core parity, native presplash configuration and security preflight
checks passed. The bundled SQLite seed was restored from a local source and passed
the repository's pinned size, SHA-256 and content validation.

Synthetic coverage includes multiple distinct tails, unchanged legacy fields,
wrong versions/digests, truncation, duplicates, extra bytes, shop read-only
enrichment, database upgrades/rollback and recipe-only reads, and ten-table
dynamic runtime activation followed by invalidation on changed ItemData.
Synthetic digest substitutions are confined to tests.

Run the focused suite from the repository root with `tests` on `PYTHONPATH`:

```sh
python -m unittest discover -s tests -p 'test_itemdata*.py' -v
```

To validate private real data, install the pinned development dependencies
and set `WLRE_ITEMDATA_1296_BUNDLE` to the cached official 1296
`datapackage_data_i.bundle`, then run the same command. The private test
requires exactly one expected TextAsset, checks its digest, parses all 11,366
records and compares every opaque tail against the original bytes. It never
uploads or copies official resources into the repository.

Actual 1296 bundle validation, full Android regression with Kivy/PyJNIUS,
ARM64 APK compilation, installation, UI, login and live gameplay have not been
validated by these host tests. No version bump, main merge, tag or Release was
performed as part of host validation.
