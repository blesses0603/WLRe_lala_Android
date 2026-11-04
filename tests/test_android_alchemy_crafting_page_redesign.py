"""One-page Android P4 redesign: only the paired alchemy/crafting workspace.

No claims of phone screenshot parity here: CI tests Kivy structure, live
material data, safe preview and the existing server confirmation boundary.
"""
import ast
import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import unittest

ROOT = Path(__file__).resolve().parents[1]
HAS_KIVY = importlib.util.find_spec("kivy") is not None


class ProductionScreenOffline(unittest.TestCase):
    def test_compact_mode_is_only_used_by_the_paired_screen(self):
        production = (ROOT / "android_app/pages/production.py").read_text("utf-8")
        combined = (ROOT / "android_app/pages/combined.py").read_text("utf-8")
        ast.parse(production)
        ast.parse(combined)
        self.assertIn("def __init__(self, d, compact=False):", production)
        self.assertIn("self.material_grid = GridLayout(", production)
        self.assertIn("'cols', 2 if width < dp(285) else 3", production)
        self.assertIn("self._show_material_icon(index, None)", production)
        self.assertIn("self.catalog = GridLayout(", production)
        self.assertIn("def preview_recipe(self, recipe):", production)
        self.assertIn("def open_preview(self):", production)
        self.assertIn("compact = self.pair_name == '煉金＋製作'", combined)
        self.assertIn("page_type(proxy, compact=True)", combined)
        self.assertIn("if compact else page_type(proxy)", combined)

    def test_all_protected_operations_remain_in_original_controller(self):
        production = (ROOT / "android_app/pages/production.py").read_text("utf-8")
        for key in ("prepare(state, command)", "'start_alchemy'",
                    "'stop_alchemy'", "recipe_plan(state, sid, number)",
                    "confirmed_unlocked(", "validate_rows(",
                    "action='enter'", "action='start'",
                    "action='pause'", "action='stop_auto'",
                    "self.d.send(command, text"):
            with self.subTest(key=key):
                self.assertIn(key, production)


@unittest.skipUnless(HAS_KIVY and (os.environ.get("DISPLAY") or os.name == "nt"),
                     "Requires a Kivy graphical display")
class ProductionScreenKivy(unittest.TestCase):
    def make_d(self):
        sent = []
        dashboard = SimpleNamespace(
            page_name='', data={'preferences': {'favorites': [], 'plan': []}},
            state={'inventory': {'ready': True, 'items': {}},
                   'furniture': {}, 'crafting': {'queue': {}},
                   'alchemy': {}},
            live=False, closed=False, message=SimpleNamespace(text=''),
            send=lambda *args: sent.append(args))
        return dashboard, sent

    def test_compact_alchemy_shows_five_real_touch_slots_not_five_cards(self):
        from kivy.uix.widget import Widget
        from android_app.pages.production import Alchemy
        d, sent = self.make_d()
        with patch('android_app.pages.production.item_image',
                   side_effect=lambda *args, **kw: Widget(
                       size_hint=(None, None), size=(52, 52))), \
             patch('android_app.pages.production.item_name',
                   return_value='測試原圖材料'):
            a = Alchemy(d, compact=True)
            self.assertEqual(len(a.slots), 5)
            self.assertEqual(len(a.material_grid.children), 5)
            self.assertEqual(a.material_grid.cols, 2)
            self.assertEqual(len(a.material_icons), 5)
            self.assertEqual(len(a.material_icons[0].children), 1)
            self.assertEqual(a.slots[0][1].text, '1')
            a.set_slot(0, {'index': 7, 'item_id': 10001, 'count': 4})
            self.assertIn('格位 #7', a.slots[0][0].text)
            self.assertEqual(len(a.material_icons[0].children), 1)
            self.assertEqual(a.materials[0]['item_id'], 10001)
            a.clear()
            self.assertEqual(a.materials, [None]*5)
            self.assertIn('選擇材料', a.slots[0][0].text)
            self.assertEqual(sent, [])
            normal = Alchemy(d)
            self.assertFalse(normal.compact)
            self.assertFalse(hasattr(normal, 'material_grid'))
            self.assertEqual(len(normal.slots), 5)

    def test_compact_crafting_has_inline_recipe_info_but_no_auto_enqueue(self):
        from kivy.uix.widget import Widget
        from kivy.uix.gridlayout import GridLayout
        from android_app.pages.production import Crafting
        d, sent = self.make_d()
        recipe = {'item_id': 10001, 'tool_id': 20001,
                  'output': 2, 'seconds': 90}
        with patch('android_app.pages.production.RECIPES',
                   {'10001': recipe}), \
             patch('android_app.pages.production.confirmed_unlocked',
                   return_value=True), \
             patch('android_app.pages.production.item_name',
                   side_effect=lambda i: '測試物品 '+str(i)), \
             patch('android_app.pages.production.availability',
                   return_value=('已核對', '尚未符合伺服器操作條件')), \
             patch('android_app.pages.production.tool_status',
                   return_value='尚未擺放'), \
             patch('android_app.pages.production.material_rows',
                   return_value=[{'name':'測試原料','usable':3,'required':5}]), \
             patch('android_app.pages.production.item_image',
                   side_effect=lambda *args, **kw: Widget(
                       size_hint=(None, None), size=(52, 52))):
            c = Crafting(d, compact=True)
            self.assertIsInstance(c.catalog, GridLayout)
            self.assertTrue(c.preview_action.disabled)
            c.refresh()
            self.assertEqual(len(c.catalog.children), 1)
            self.assertTrue(c.preview_action.disabled)
            c.preview_recipe(recipe)
            self.assertFalse(c.preview_action.disabled)
            self.assertIn('測試原料：可用 3／需求 5',
                          c.preview_info.text)
            self.assertIn('尚未符合伺服器操作條件',
                          c.preview_info.text)
            self.assertEqual(sent, [])
            with patch.object(c, 'recipe') as open_detail:
                c.open_preview()
                open_detail.assert_called_once_with(recipe)
                self.assertEqual(sent, [])
            c.selected = 99999
            c._render_preview()
            self.assertTrue(c.preview_action.disabled)
            self.assertEqual(sent, [])
            standalone = Crafting(d)
            self.assertFalse(standalone.compact)
            self.assertFalse(hasattr(standalone, 'preview_action'))


if __name__ == '__main__':
    unittest.main()
