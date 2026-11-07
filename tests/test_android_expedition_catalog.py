"""Current expedition UI catalog changes must invalidate old task selection."""
import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch

@unittest.skipUnless(os.environ.get('DISPLAY') or os.name=='nt','Requires Kivy display')
class ExpeditionCatalogRefreshTests(unittest.TestCase):
    def test_cold_page_has_explicit_unavailable_catalog(self):
        from android_app.pages.expedition import Expedition
        with patch('android_app.pages.expedition.load_catalog',side_effect=ValueError('unavailable')):
            self.assertEqual(Expedition._load_catalog()['source_kind'],'formal_sources_missing')

    def test_new_generation_clears_selection_and_rerenders_same_ids(self):
        from android_app.pages.expedition import Expedition
        page=SimpleNamespace(_catalog_token=('old',),catalog={'tasks':{'1':{'name':'old'}}},
             signature='old',current=1,quest_detail=SimpleNamespace(text='old'))
        page._load_catalog=lambda:{'tasks':{'1':{'name':'new'}}}
        with patch('android_app.pages.expedition.current_catalog_token',return_value=('new',)):
            Expedition.refresh_catalog(page)
        self.assertEqual(page.catalog['tasks']['1']['name'],'new')
        self.assertIsNone(page.current)
        self.assertIsNone(page.signature)
        self.assertIn('重新選擇',page.quest_detail.text)

    def test_failed_generation_removes_previous_catalog(self):
        from android_app.pages.expedition import Expedition
        page=SimpleNamespace(_catalog_token=('old',),catalog={'tasks':{'1':{}}},
             signature='old',current=1,quest_detail=SimpleNamespace(text='old'))
        page._load_catalog=lambda:{'tasks':{},'source_kind':'formal_sources_missing'}
        with patch('android_app.pages.expedition.current_catalog_token',return_value=('failed',)):
            Expedition.refresh_catalog(page)
        self.assertFalse(page.catalog['tasks'])
        self.assertIsNone(page.current)
