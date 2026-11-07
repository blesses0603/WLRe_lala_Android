"""Full runtime integration from synthetic verified manifests and TextAssets."""
from contextlib import ExitStack, closing
from copy import deepcopy
import hashlib
import sqlite3
import struct
import unittest
from unittest.mock import patch

from test_eve_v115 import fixture as eve_fixture
from test_itemdata_v1 import sample as item_record
from test_npc_talk_v058 import sample_record as talk_record
import test_official_catalog_pipeline as pipeline_fixtures
from wlre.network.wire import Writer
from wlre.services.world import dynamic_bundle_runtime as dynamic
from wlre.services.world.bundle_runtime_1275 import _REQUIRED_TABLES, _ASSET_ROOT
from wlre.services.world.official_catalog_store import store_official_catalog, active_official_catalog
from wlre.services.world.catalog_adapters import FEATURES, ParsedCatalog


class DynamicBundleRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.fixture = pipeline_fixtures.OfficialPipelineTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.snapshot = deepcopy(self.fixture.snapshot)
        # Different package revisions are deliberately supported.
        self.snapshot['packages']['DataPackage'] = '1286_2026_10_29_13_42_37_94'
        self.snapshot['packages']['MainPackage'] = '1284_2026_10_28_19_50_04_11'
        from dataclasses import replace
        self.manifests = {}
        for name, old in self.fixture.manifests.items():
            index = deepcopy(old.index)
            index['header']['package_version'] = self.snapshot['packages'][name]
            if name == 'DataPackage':
                index['assets'] = [{'path': _ASSET_ROOT + t + '.bytes',
                                    'bundle_name': index['bundles'][0]['name']}
                                   for t in _REQUIRED_TABLES]
            self.manifests[name] = replace(old,
                spec=replace(old.spec, package_version=self.snapshot['packages'][name]), index=index)
        from wlre.services.official_bundle_download import spec_from_manifest
        for name, manifest in self.manifests.items():
            old = self.fixture.manifests[name]
            for row in manifest.index['bundles']:
                original = spec_from_manifest(data_ver=old.spec.data_ver, package=name,
                    index=old.index, name=row['name']).cache_path(self.fixture.bundle_root)
                new = spec_from_manifest(data_ver=manifest.spec.data_ver, package=name,
                    index=manifest.index, name=row['name']).cache_path(self.fixture.bundle_root)
                new.parent.mkdir(parents=True, exist_ok=True)
                new.write_bytes(original.read_bytes())
        recipe = bytearray(33)
        struct.pack_into('<H', recipe, 0, 3874)
        recipe[7] = 1
        struct.pack_into('<H', recipe, 24, 5)
        stage = bytearray(76)
        struct.pack_into('<H', stage, 0, 500)
        struct.pack_into('<I', stage, 4, 10)
        struct.pack_into('<H', stage, 8, 123)
        struct.pack_into('<HH', stage, 52, 1000, 1000)
        npc = bytearray(203)
        struct.pack_into('<H', npc, 1, 9001)
        task = (Writer().u16(1).u8(1).u32(20).u8(1).u32(10).u32(10)
                .u16(300).u8(10).u16(80))
        for _ in range(3): task.u16(0)
        for _ in range(4): task.u16(0).u16(0).u16(0).u16(0)
        task.u32(100)
        for _ in range(3): task.u8(0).u32(0).u32(0)
        task.u16(0).u8(0).u32(0).u32(0).u32(50)
        def text(key, value):
            raw = value.encode('utf-16-le')
            return struct.pack('<IH', key, len(raw)) + raw
        self.raw = {
            'Eve': eve_fixture(),
            'ItemData_C': struct.pack('<i', 1) + item_record(iid=3874),
            'SmithData_C': struct.pack('<iH', 1, 99) + recipe,
            'ScenesData_C': struct.pack('<i', 1) + stage,
            'TalkData_C': struct.pack('<i', 1) + talk_record(),
            'TextData_C': struct.pack('<i', 2) + text(10, '新版任務') + text(20, '新版地區'),
            'AdventureData_C': struct.pack('<i', 1) + task.build(),
            'AdventureLvData_C': struct.pack('<i', 1) + struct.pack('<BIIBBHBB', 1, 0, 0, 2, 1, 0, 0, 0),
            'NpcData_C': struct.pack('<iHH', 1, 0, 0) + npc,
            'NpcCareerData_C': struct.pack('<i', 0),
        }
        self.remote = {'resource_path': self.snapshot['data_ver'],
                       'official_exe_version': self.snapshot['exe_version'],
                       'newer_official_client': False,
                       'packages': {k: {'remote': v} for k, v in self.snapshot['packages'].items()}}
        self.stack = self.enterContext(ExitStack())
        self.stack.enter_context(patch('wlre.services.world.unity_textasset.extract_textasset',
            side_effect=lambda binding, paths, loader=None: self.raw[binding.contract.source_name]))
        self.stack.enter_context(patch.object(dynamic, '_active', None))
        self.stack.enter_context(patch.object(dynamic, '_attempted', False))
        from wlre.services.items.crafting import RECIPES
        saved = deepcopy(RECIPES)
        self.addCleanup(lambda: (RECIPES.clear(), RECIPES.update(saved)))

    def kwargs(self):
        return dict(sync_root=self.root, observe=lambda: deepcopy(self.snapshot),
                    retrieve=lambda spec, cache_root: self.manifests[spec.package])

    def test_1296_itemdata_version_tail_and_failed_refresh_invalidate_runtime(self):
        from dataclasses import replace
        from wlre.services.official_bundle_download import spec_from_manifest
        from wlre.services.world import itemdata_v1
        version = '1296_2026_11_04_13_34_19_13'
        old = self.manifests['DataPackage']
        index = deepcopy(old.index)
        index['header']['package_version'] = version
        current = replace(old, spec=replace(old.spec, package_version=version), index=index)
        for row in current.index['bundles']:
            previous = spec_from_manifest(data_ver=old.spec.data_ver, package='DataPackage',
                index=old.index, name=row['name']).cache_path(self.fixture.bundle_root)
            target = spec_from_manifest(data_ver=current.spec.data_ver, package='DataPackage',
                index=current.index, name=row['name']).cache_path(self.fixture.bundle_root)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(previous.read_bytes())
        self.manifests['DataPackage'] = current
        self.snapshot['packages']['DataPackage'] = version
        self.remote['packages']['DataPackage']['remote'] = version
        self.raw['ItemData_C'] = (struct.pack('<I', 2) + item_record(3874) + b'\x00\xff'
                                 + item_record(3875) + b'\x12\x34')
        with patch.object(itemdata_v1, 'ITEMDATA_1296_SHA256',
                          hashlib.sha256(self.raw['ItemData_C']).hexdigest()), patch.object(
                itemdata_v1, 'parse_itemdata', wraps=itemdata_v1.parse_itemdata) as parse:
            runtime = dynamic.activate_for_official(self.remote, **self.kwargs())
            parse.assert_called_once_with(self.raw['ItemData_C'], package_version=version)
            self.assertEqual(runtime.revision, 1296)
            self.assertEqual(runtime.record_counts['items'], 2)
            self.assertEqual(runtime.items[3874]['unknown_tail_1296_hex'], '00ff')
            self.assertEqual(runtime.items[3875]['unknown_tail_1296_hex'], '1234')
            self.assertEqual(self.snapshot['packages']['MainPackage'],
                             '1284_2026_10_28_19_50_04_11')
            self.assertFalse(runtime.can_send_packets)
            self.raw['ItemData_C'] = self.raw['ItemData_C'][:-1] + b'\x35'
            with self.assertRaisesRegex(ValueError, 'ItemData_C'):
                dynamic.activate_for_official(self.remote, **self.kwargs())
            self.assertIsNone(dynamic.current_runtime())
            from wlre.services.items.crafting import RECIPES
            self.assertEqual(RECIPES, {})

    def test_smallmap_publication_is_bound_to_same_runtime_and_failure_clears_it(self):
        from wlre.services.world.smallmap_database import import_images, PREFIX
        from wlre.services.world.smallmaps import SmallMaps
        from PIL import Image
        # Add valid current projection fields to the synthetic ScenesData.
        stage=bytearray(self.raw['ScenesData_C'])
        struct.pack_into('<HH',stage,4+52,1000,1000)
        self.raw['ScenesData_C']=bytes(stage)
        path=PREFIX+'SmallMap2D_123.png'
        def verified(manifest,bundles,root,identity):
            return import_images(root/'derived_catalogs'/'official_images.sqlite3',identity.key,
                {'verified_test':'source'},(path,),lambda:iter([(path,Image.new('RGBA',(1024,1024),'blue'))]))
        with patch('wlre.services.world.smallmap_database.load_verified_images',side_effect=verified):
            runtime=dynamic.activate_for_official(self.remote,**self.kwargs())
            maps=SmallMaps();self.assertTrue(maps.has_image(500))
            self.assertEqual(maps.image('M00123').size,(1024,1024))
        with patch('wlre.services.world.smallmap_database.load_verified_images',side_effect=ValueError('source invalid')):
            runtime=dynamic.activate_for_official(self.remote,**self.kwargs())
            self.assertIsNone(runtime.smallmaps)
            self.assertFalse(maps.has_image(500))
            self.assertFalse(SmallMaps().has_image(500))

    def test_battle_talk_current_text_join_and_source_failure(self):
        from test_npc_battle_catalog import fixture
        from wlre.services.world import npc_battle_catalog as catalog
        from wlre.services.world.npc_localization import load_battle_talk
        raw,_=fixture()
        # Use current runtime's existing Text IDs (10/20).
        raw=raw.replace(struct.pack('<I',100),struct.pack('<I',10)).replace(struct.pack('<I',101),struct.pack('<I',20))
        manifest=self.manifests['DataPackage']
        manifest.index['assets'].append(dict(path=_ASSET_ROOT+'NpcTalkData_C.bytes',
            bundle_name=manifest.index['bundles'][0]['name']))
        self.raw['NpcTalkData_C']=raw
        with patch.object(catalog,'KNOWN_SHA256',hashlib.sha256(raw).hexdigest()):
            runtime=dynamic.activate_for_official(self.remote,**self.kwargs())
            self.assertEqual(len(load_battle_talk()[1]),2)
            self.raw['NpcTalkData_C']=b'unknown'
            runtime=dynamic.activate_for_official(self.remote,**self.kwargs())
            self.assertIsNone(runtime.battle_talk)
            with self.assertRaises(ValueError):load_battle_talk()

    def test_instances_verified_tables_database_update_and_invalid_source(self):
        from test_instance_catalog_1262 import payloads
        from wlre.services.world.instance_runtime import TABLES
        from wlre.services.instance_browser import entries_for, selection_fields, selected_entry
        raw=payloads()
        self.raw.update(raw)
        manifest=self.manifests['DataPackage']
        manifest.index['assets'].extend(dict(path=_ASSET_ROOT+t+'.bytes',
            bundle_name=manifest.index['bundles'][0]['name']) for t in TABLES)
        runtime=dynamic.activate_for_official(self.remote,**self.kwargs())
        self.assertIsNotNone(runtime.instances, runtime.instance_status)
        chosen=entries_for('main')[0]
        self.assertEqual(selected_entry('main',selection_fields(chosen)),chosen)
        # Rebuild from the same verified source/database; unknown bytes must
        # disable only this feature and never revive the bundled catalog.
        self.raw['DungeonData_C']=b'unknown'
        runtime=dynamic.activate_for_official(self.remote,**self.kwargs())
        self.assertIsNone(runtime.instances)
        self.assertEqual(entries_for('main'),())
        with self.assertRaises(ValueError):selected_entry('main',selection_fields(chosen))
        self.raw['DungeonData_C']=raw['DungeonData_C']
        runtime=dynamic.activate_for_official(self.remote,**self.kwargs())
        self.assertIsNotNone(runtime.instances, runtime.instance_status)

    def test_full_parsing_activation_and_all_consumers_use_current_data(self):
        runtime = dynamic.activate_for_official(self.remote, **self.kwargs())
        self.assertEqual(runtime.revision, 1286)
        self.assertEqual(runtime.record_counts,
                         dict(npc=1, shops=1, items=1, crafting=1, scenes=1, expedition=1))
        self.assertEqual(runtime.recipe_catalog[0]['recipe_id'], 99)
        self.assertEqual(set(runtime.source_sha256), set(_REQUIRED_TABLES))
        from wlre.services.world.runtime_1275 import active_runtime, baseline_revision
        from wlre.services.world.catalog_source_policy import official_runtime, source_for
        from wlre.services.world.npc_catalog import NPCIndex
        from wlre.services.world.npc_interact import NPCInteractIndex
        from wlre.services.world.npc_talk import load_catalog
        from wlre.services.world.npc_item_data import item_catalog
        from wlre.services.items.catalog import item_name, verified_item_metadata
        from wlre.services.expedition.data import load_active_catalog
        from wlre.services.items.crafting import RECIPES, confirmed_unlocked, recipe_plan
        from wlre.core.state import State
        self.assertIs(active_runtime(), runtime)
        self.assertEqual(baseline_revision(), '1286')
        for feature in ('npc', 'items', 'maps', 'crafting', 'expedition'):
            self.assertIs(official_runtime(feature), runtime)
            self.assertFalse(source_for(feature).gameplay_allowed)
        self.assertEqual(NPCIndex().for_scene(500)[0]['npc_id'], 9001)
        self.assertEqual(NPCInteractIndex().get(500, 8)['form_kind'], 3)
        self.assertIn(411, load_catalog())
        self.assertEqual(item_catalog(), runtime.items)
        self.assertEqual(item_name(3874), '蘋果')
        self.assertEqual(verified_item_metadata(3874)['source_revision'], 1286)
        self.assertEqual(load_active_catalog()['tasks']['1']['name'], '新版任務')
        self.assertTrue(confirmed_unlocked(RECIPES['3874']))
        with self.assertRaisesRegex(ValueError, '帳篷'):
            recipe_plan(State(), 3874, 1)
        self.assertFalse(runtime.can_send_packets)

    def test_unknown_smith_layout_and_corrupt_item_table_refuse_activation(self):
        for name in ('SmithData_C', 'ItemData_C'):
            with self.subTest(name=name):
                original = self.raw[name]
                self.raw[name] += b'\xff'
                with self.assertRaises(ValueError):
                    dynamic.activate_for_official(self.remote, **self.kwargs())
                self.assertIsNone(dynamic.current_runtime())
                self.raw[name] = original

    def test_missing_item_id_in_shop_refuses_runtime(self):
        self.raw['ItemData_C'] = struct.pack('<i', 1) + item_record(iid=999)
        with self.assertRaisesRegex(ValueError, '商店商品'):
            dynamic.prepare_dynamic_runtime(**self.kwargs())

    def test_changed_live_pair_and_mismatched_prelogin_identity_refuse(self):
        changed = deepcopy(self.snapshot)
        changed['packages']['MainPackage'] = '1285_2026_10_29_19_50_04_11'
        observations = iter((self.snapshot, changed))
        with self.assertRaisesRegex(ValueError, 'changed'):
            dynamic.prepare_dynamic_runtime(**dict(self.kwargs(), observe=lambda: next(observations)))
        self.remote['packages']['MainPackage']['remote'] = changed['packages']['MainPackage']
        with self.assertRaisesRegex(ValueError, 'pre-login'):
            dynamic.activate_for_official(self.remote, **self.kwargs())
        self.assertIsNone(dynamic.current_runtime())

    def test_tampered_cached_manifest_and_bundle_rejected(self):
        manifest = self.manifests['DataPackage']
        original = manifest.cache_path.read_bytes()
        manifest.cache_path.write_bytes(original + b'!')
        with self.assertRaisesRegex(ValueError, 'CRC'):
            dynamic.prepare_dynamic_runtime(**self.kwargs())
        manifest.cache_path.write_bytes(original)
        for path in self.fixture.bundle_root.rglob('*.bundle'):
            path.write_bytes(b'tampered')
        with self.assertRaises(ValueError):
            dynamic.prepare_dynamic_runtime(**self.kwargs())

    def test_failure_invalidates_previous_runtime_and_never_uses_legacy(self):
        dynamic.activate_for_official(self.remote, **self.kwargs())
        self.raw['Eve'] = b'changed schema'
        with self.assertRaises(ValueError):
            dynamic.activate_for_official(self.remote, **self.kwargs())
        from wlre.services.world.runtime_1275 import active_runtime
        from wlre.services.items.crafting import RECIPES
        from wlre.services.expedition.data import load_active_catalog
        with self.assertRaisesRegex(ValueError, '禁止退回'):
            active_runtime()
        with self.assertRaises(ValueError):
            load_active_catalog()
        self.assertEqual(RECIPES, {})

    def test_duplicate_product_recipes_remain_in_complete_catalog(self):
        raw = self.raw['SmithData_C']
        raw = struct.pack('<i', 2) + raw[4:] + struct.pack('<H', 100) + raw[6:]
        from wlre.services.world.itemdata_v1 import parse_itemdata
        unique, rows = dynamic.parse_runtime_recipes(raw, parse_itemdata(self.raw['ItemData_C']))
        self.assertEqual(unique, {})
        self.assertEqual([r['recipe_id'] for r in rows], [99, 100])

    def test_superseded_background_load_cannot_publish_stale_data(self):
        runtime = dynamic.prepare_dynamic_runtime(**self.kwargs())
        def newer_check(**kwargs):
            dynamic.invalidate_runtime()
            return runtime
        with patch.object(dynamic, 'prepare_dynamic_runtime', side_effect=newer_check):
            with self.assertRaisesRegex(ValueError, 'superseded'):
                dynamic.activate_for_official(self.remote)
        self.assertIsNone(dynamic.current_runtime())

    def test_sync_rechecks_versions_before_writing_bundles(self):
        changed = deepcopy(self.snapshot)
        changed['packages']['MainPackage'] = '1285_2026_10_29_19_50_04_11'
        observed = iter((self.snapshot, changed))
        from unittest.mock import Mock
        execute = Mock()
        with self.assertRaisesRegex(ValueError, 'before Bundle'):
            dynamic.prepare_dynamic_runtime(sync=True, execute=execute,
                **dict(self.kwargs(), observe=lambda: next(observed)))
        execute.assert_not_called()


class OfficialCatalogMigrationTests(unittest.TestCase):
    def test_four_source_database_upgrades_without_losing_history(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'catalog.sqlite3'
            with closing(sqlite3.connect(path)) as db, db:
                db.execute('CREATE TABLE official_catalog_versions '
                           '(catalog_key TEXT PRIMARY KEY, verified_count INTEGER NOT NULL CHECK(verified_count=4))')
                db.execute('INSERT INTO official_catalog_versions VALUES (?,4)', ('a'*64,))
            parsed = {f: ParsedCatalog('b'*64, f, f+'.bytes', 'schema-v1', 'c'*64, 1, {}) for f in FEATURES}
            store_official_catalog(path, parsed)
            with closing(sqlite3.connect(path)) as db, db:
                self.assertEqual(db.execute('SELECT verified_count FROM official_catalog_versions ORDER BY catalog_key').fetchall(), [(4,), (5,)])
            self.assertEqual(set(active_official_catalog(path)['sources']), set(FEATURES))
