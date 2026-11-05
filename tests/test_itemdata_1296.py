"""Synthetic 1296 regressions; private official resources are never bundled."""
import hashlib
import os
from pathlib import Path
import sqlite3
import struct
import tempfile
import unittest
from contextlib import closing
from unittest.mock import patch

from test_itemdata_v1 import sample
from wlre.services.world import itemdata_v1 as itemdata
from wlre.services.world.catalog_adapters import (
    CatalogAdapterError, SourceContract, parse_feature,
)


VERSION = '1296_2026_11_04_13_34_19_13'
LEGACY = '1286_2026_10_29_13_42_37_94'


def payload(*records):
    return struct.pack('<I', len(records)) + b''.join(records)


class ItemData1296Tests(unittest.TestCase):
    def setUp(self):
        self.raw = payload(sample(10) + b'\x00\xff', sample(11) + b'\x12\x34')
        self.enterContext(patch.object(itemdata, 'ITEMDATA_1296_SHA256',
                                       hashlib.sha256(self.raw).hexdigest()))

    def test_two_records_preserve_every_tail_byte_and_existing_fields(self):
        rows = itemdata.parse_itemdata(self.raw, package_version=VERSION)
        legacy = itemdata.parse_itemdata(payload(sample(10), sample(11)))
        self.assertEqual(list(rows), [10, 11])
        for iid, tail in ((10, b'\x00\xff'), (11, b'\x12\x34')):
            self.assertEqual(bytes.fromhex(rows[iid]['unknown_tail_1296_hex']), tail)
            self.assertEqual({k: rows[iid][k] for k in legacy[iid]}, legacy[iid])
            self.assertEqual(rows[iid]['style_bank_set_sort_id'], int.from_bytes(tail, 'little'))
            self.assertIn('icon_id', rows[iid])
        self.assertEqual(itemdata.parse_itemdata(self.raw), rows)

    def test_legacy_versions_keep_unchanged_dictionaries(self):
        raw = payload(sample(10), sample(11))
        expected = itemdata.parse_itemdata(raw)
        for version in itemdata.LEGACY_ITEMDATA_VERSIONS:
            with self.subTest(version=version):
                self.assertEqual(itemdata.parse_itemdata(raw, package_version=version), expected)
                self.assertNotIn('unknown_tail_1296_hex', expected[10])

    def test_wrong_legacy_future_or_timestamp_version_is_rejected(self):
        versions = (*itemdata.LEGACY_ITEMDATA_VERSIONS, '1296',
                    '1296_2026_11_04_13_34_19_14', '1297_2026_11_05_00_00_00_00',
                    '', 1296, [], {})
        for version in versions:
            with self.subTest(version=version), self.assertRaises(itemdata.ItemDataDecodeError):
                itemdata.parse_itemdata(self.raw, package_version=version)

    def test_changed_hash_is_not_accepted_by_a_known_1296_version(self):
        for raw in (self.raw[:-1], self.raw + b'\x00',
                    self.raw[:-2] + b'\x56\x78', payload(sample(10), sample(11))):
            with self.subTest(size=len(raw)), self.assertRaisesRegex(
                    itemdata.ItemDataDecodeError, 'digest mismatch'):
                itemdata.parse_itemdata(raw, package_version=VERSION)

    def test_unknown_extended_payload_never_falls_back_to_guessing_layout(self):
        with patch.object(itemdata, 'ITEMDATA_1296_SHA256', '0' * 64):
            with self.assertRaises(itemdata.ItemDataDecodeError):
                itemdata.parse_itemdata(self.raw)

    def test_truncated_or_extra_payload_rejected_even_with_matching_test_hash(self):
        for raw in (self.raw[:-1], self.raw + b'\x00', self.raw + b'\x00\x00'):
            with self.subTest(size=len(raw)), patch.object(
                    itemdata, 'ITEMDATA_1296_SHA256', hashlib.sha256(raw).hexdigest()):
                with self.assertRaises(itemdata.ItemDataDecodeError):
                    itemdata.parse_itemdata(raw, package_version=VERSION)

    def test_duplicate_id_and_invalid_unicode_still_fail_on_1296_layout(self):
        duplicate = payload(sample(10) + b'\x00\xff', sample(10) + b'\x12\x34')
        invalid = bytearray(self.raw)
        invalid[4] = 3
        for raw in (duplicate, bytes(invalid)):
            with patch.object(itemdata, 'ITEMDATA_1296_SHA256', hashlib.sha256(raw).hexdigest()):
                with self.assertRaises(itemdata.ItemDataDecodeError):
                    itemdata.parse_itemdata(raw, package_version=VERSION)

    def test_adapter_uses_full_datapackage_version_and_remains_read_only(self):
        for version in (VERSION, LEGACY, '1297_2026_11_05_00_00_00_00'):
            contract = SourceContract('items', 'ItemData_C', 'itemdata-v1',
                hashlib.sha256(self.raw).hexdigest(), 'DataPackage', version)
            kwargs = dict(catalog_key='a' * 64, contract=contract, raw=self.raw,
                          package_versions={'DataPackage': version, 'MainPackage': LEGACY})
            if version == VERSION:
                parsed = parse_feature(**kwargs)
                self.assertEqual(parsed.record_count, 2)
                self.assertEqual(parsed.records[11]['unknown_tail_1296_hex'], '1234')
                self.assertFalse(parsed.can_send_packets)
                self.assertFalse(parsed.assets_ready)
            else:
                with self.assertRaises(CatalogAdapterError):
                    parse_feature(**kwargs)

    def test_database_keeps_raw_and_opaque_rows_across_legacy_transition(self):
        from wlre.services.world.resource_database import record_inventory, read_catalog_tables
        old = payload(sample(10), sample(11))
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / 'resources.sqlite3'
            record_inventory(database, 'a' * 64, {'tables/ItemData_C.bytes': old})
            result = record_inventory(database, 'b' * 64, {'tables/ItemData_C.bytes': self.raw})
            self.assertEqual(result['item_rows']['changed'], ['10', '11'])
            rows = read_catalog_tables(database, 'b' * 64, ['items'])['items']
            self.assertEqual(rows[10]['unknown_tail_1296_hex'], '00ff')
            self.assertNotIn('unknown_tail_1296_hex',
                read_catalog_tables(database, 'a' * 64, ['items'])['items'][10])
            with closing(sqlite3.connect(database)) as db:
                stored = db.execute('SELECT data FROM resources JOIN versions '
                    'ON versions.id=resources.version_id WHERE catalog_key=?', ('b' * 64,)).fetchone()[0]
            self.assertEqual(stored, self.raw)
            rollback = record_inventory(database, 'a' * 64, {'tables/ItemData_C.bytes': old})
            self.assertEqual(rollback['item_rows']['changed'], ['10', '11'])

    def test_shop_enrichment_preserves_tail_without_authorizing_purchase(self):
        import json
        from wlre.services.world.catalog_source_extractor import extract_catalog_source
        from wlre.services.world.official_catalog_pipeline import AssetBinding
        document = {'schema_version': 1, 'source': 'EventData.NewInteract',
                    'record_count': 1, 'scenes': {'500': [{'index': 8,
                        'form_kind': 3, 'items': [{'id': 1, 'text_id': 10,
                                                 'database_kind': 2, 'kind': 3}]}]}}
        for version in (VERSION, LEGACY):
            contract = SourceContract('shops', 'EventData.NewInteract',
                'eve-interact-json-v1', '0' * 64, 'DataPackage', version)
            binding = AssetBinding('Assets/ResourcesBuild/Data/Eve.bytes', contract,
                                   ('Assets/ResourcesBuild/Data/ItemData_C.bytes',))
            with patch('wlre.services.world.catalog_source_extractor.extract_textasset',
                       side_effect=(b'eve', self.raw)), patch(
                    'wlre.services.world.catalog_source_extractor.derive_eve_index',
                    return_value=json.dumps(document).encode()):
                if version == VERSION:
                    result = json.loads(extract_catalog_source(binding, ()))
                    offer = result['scenes']['500'][0]['items'][0]
                    self.assertEqual(offer['item_data']['unknown_tail_1296_hex'], '00ff')
                    self.assertEqual(offer['item_data']['price'], 125)
                    self.assertFalse(offer['buy_enabled'])
                    self.assertEqual(result['itemdata_sha256'], hashlib.sha256(self.raw).hexdigest())
                else:
                    with self.assertRaises(itemdata.ItemDataDecodeError):
                        extract_catalog_source(binding, ())

    def test_recipe_only_database_read_checks_1296_items(self):
        from wlre.services.world.resource_database import record_inventory, read_catalog_tables
        recipes = [{'item_id': 10, 'candidate_row_key': 1, 'time_id': 0,
                    'materials': [{'item_id': 11}]}]
        with tempfile.TemporaryDirectory() as directory, patch(
                'wlre.services.world.smith_candidate.parse_smith_records', return_value=recipes):
            database = Path(directory) / 'resources.sqlite3'
            record_inventory(database, 'a' * 64, {'tables/ItemData_C.bytes': self.raw,
                                                 'tables/SmithData_C.bytes': b'synthetic'})
            self.assertEqual(len(read_catalog_tables(database, 'a' * 64, ['recipes'])['recipes']), 1)


class PrivateItemData1296Tests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('WLRE_ITEMDATA_1296_BUNDLE'),
                         'private official 1296 bundle not supplied')
    def test_private_official_bundle_and_all_tail_bytes(self):
        import UnityPy
        from wlre.services.world.unity_textasset import _payload
        env = UnityPy.load(str(Path(os.environ['WLRE_ITEMDATA_1296_BUNDLE'])))
        matches = [_payload(obj, path) for path, obj in env.container.items()
                   if path.lower() == 'assets/resourcesbuild/data/itemdata_c.bytes']
        self.assertEqual(len(matches), 1)
        raw = matches[0]
        self.assertEqual(hashlib.sha256(raw).hexdigest(),
                         '5195d5ee8ae201dea55439274914930551176c3fcf50d735e03b09c5d04acbb4')
        starts = []
        original = itemdata.Reader.utf16

        def read_name(reader, *, allow_empty=False):
            if not allow_empty:
                starts.append(reader.pos)
            return original(reader, allow_empty=allow_empty)

        with patch.object(itemdata.Reader, 'utf16', read_name):
            rows = itemdata.parse_itemdata(raw, package_version=VERSION)
        self.assertEqual(len(rows), 11366)
        self.assertEqual(len(starts), len(rows))
        for row, end in zip(rows.values(), starts[1:] + [len(raw)]):
            self.assertEqual(bytes.fromhex(row['unknown_tail_1296_hex']), raw[end - 2:end])


if __name__ == '__main__':
    unittest.main()
