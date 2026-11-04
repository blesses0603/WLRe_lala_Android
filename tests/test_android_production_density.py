"""v7.1.18 Android production screenshot density / interaction regression.

Targets the user's real v7.1.17 phone captures; these checks prove widget
geometry and original command boundaries, not visual pixel-level acceptance.
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


class ProductionDensityOffline(unittest.TestCase):
    def test_only_paired_production_shell_is_compact(self):
        dashboard = (ROOT / "android_app/dashboard.py").read_text("utf-8")
        visual = (ROOT / "android_app/pages/production_visual.py").read_text("utf-8")
        production = (ROOT / "android_app/pages/production.py").read_text("utf-8")
        for source in (dashboard, visual, production):
            ast.parse(source)
        self.assertIn("compact = name == '煉金＋製作'", dashboard)
        self.assertIn("def _apply_page_density(self, name)", dashboard)
        self.assertIn("class CraftingSplit(BoxLayout):", visual)
        self.assertIn("self.crafting_panes = CraftingSplit(browse, preview)", production)
        self.assertIn("row_default_height=dp(132)", production)
        self.assertIn("height=dp(132)", visual)
        self.assertIn("height=dp(57)", visual)
        self.assertIn("self.recipe(recipe, initial_count=amount)", production)
        self.assertIn("recipe_plan(state, sid, number)", production)
        self.assertIn("prepare(state, command)", production)

    def test_no_fake_results_or_automatic_enqueue(self):
        visual = (ROOT / "android_app/pages/production_visual.py").read_text("utf-8")
        for value in ("標準煉金", "批量煉金", "指定產物", "100% 成功"):
            self.assertNotIn(value, visual)
        production = (ROOT / "android_app/pages/production.py").read_text("utf-8")
        self.assertIn("self.selected = visible[0]['item_id']", production)
        self.assertIn("def preview_recipe(self, recipe):", production)
        self.assertIn("self.preview_quantity.bind(text=lambda *_: self._render_preview())", production)


@unittest.skipUnless(
    HAS_KIVY and (os.environ.get("DISPLAY") or os.name == "nt"),
    "Requires a graphical Kivy test session")
class ProductionDensityKivy(unittest.TestCase):
    def test_crafting_panes_keep_detail_at_top_and_adapt_width(self):
        from kivy.metrics import dp
        from kivy.uix.boxlayout import BoxLayout
        from android_app.pages.production_visual import CraftingSplit
        browse = BoxLayout(size_hint_y=None, height=dp(320))
        details = BoxLayout(size_hint_y=None, height=dp(145))
        split = CraftingSplit(browse, details)
        split.width = dp(430)
        self.assertEqual(split.orientation, "horizontal")
        self.assertAlmostEqual(browse.size_hint_x, .43)
        self.assertAlmostEqual(details.size_hint_x, .57)
        self.assertEqual(details.pos_hint["top"], 1)
        self.assertEqual(split.height, dp(320))
        details.height = dp(380)
        self.assertEqual(split.height, dp(380))
        split.width = dp(340)
        self.assertEqual(split.orientation, "vertical")
        self.assertEqual(split.height,
                         browse.height + details.height + split.spacing)
        self.assertEqual(browse.size_hint_x, 1)
        self.assertEqual(details.size_hint_x, 1)

    def test_compact_chrome_restores_on_other_page(self):
        from kivy.metrics import dp
        from android_app.dashboard import Dashboard
        view = object.__new__(Dashboard)
        view.shell = SimpleNamespace(spacing=None)
        view.brand = SimpleNamespace(
            height=None, padding=None, logo=SimpleNamespace(width=None))
        view.nav_frame = SimpleNamespace(height=None, padding=None)
        view.back_button = SimpleNamespace(height=None)
        view._apply_page_density("煉金＋製作")
        self.assertEqual(view.brand.height, dp(102))
        self.assertEqual(view.nav_frame.height, dp(50))
        self.assertEqual(view.back_button.height, dp(44))
        view._apply_page_density("聊天＋組隊")
        self.assertEqual(view.brand.height, dp(112))
        self.assertEqual(view.nav_frame.height, dp(58))
        self.assertEqual(view.back_button.height, dp(48))

    def test_preview_source_quantity_and_queue_are_safe(self):
        from kivy.uix.widget import Widget
        from android_app.pages.production import Crafting
        sent = []
        recipe = {"item_id": 101, "tool_id": 201, "output": 2,
                  "seconds": 60, "materials": []}
        state = {
            "inventory": {"ready": True, "reliable": True, "items": {}},
            "crafting": {"ready": True, "queue": {}, "completed": 0},
            "furniture": {},
        }
        dashboard = SimpleNamespace(
            state=state, data={"preferences": {"favorites": [], "plan": []}},
            page_name="", live=False, message=SimpleNamespace(text=""),
            send=lambda *args: sent.append(args))
        def material_rows_for_batch(_state, _recipe, number):
            return [{"name": "已核對材料", "usable": 11, "required": number * 2}]
        with patch("android_app.pages.production.RECIPES", {"101": recipe}), \
             patch("android_app.pages.production.confirmed_unlocked",
                   return_value=True), \
             patch("android_app.pages.production.item_name",
                   side_effect=lambda sid: "物品 " + str(sid)), \
             patch("android_app.pages.production.tool_status",
                   return_value="已擺放"), \
             patch("android_app.pages.production.availability",
                   side_effect=lambda state, rec, count=1: ("可製作", "已核對")), \
             patch("android_app.pages.production.material_rows",
                   side_effect=material_rows_for_batch), \
             patch("android_app.pages.production.item_image",
                   side_effect=lambda *a, **kw: Widget(
                       size_hint=(None, None), size=(34, 34))):
            page = Crafting(dashboard, compact=True)
            page.refresh()
            self.assertEqual(page.selected, 101)
            self.assertFalse(page.preview_action.disabled)
            self.assertIn("目前沒有製作排程",
                          page.queue.children[0].text)
            self.assertEqual(sent, [])
            page.preview_quantity.text = "3"
            self.assertIn("3", page.preview_quantity.text)
            requirement = page.preview_ingredients.children[0]
            self.assertTrue(any(
                getattr(w, "text", "") == "11/6"
                for w in requirement.children))
            with patch.object(page, "recipe") as open_detail:
                page.open_preview()
                open_detail.assert_called_once_with(recipe, initial_count=3)
            self.assertEqual(sent, [])
            page.preview_quantity.text = "0"
            self.assertTrue(page.preview_action.disabled)
            page.open_preview()
            self.assertIn("有效", dashboard.message.text)
            self.assertEqual(sent, [])


if __name__ == "__main__":
    unittest.main()
