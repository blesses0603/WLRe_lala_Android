"""Android production target: actual game-grade selector + source-backed widgets.

Reference art is not loaded as a fake full-screen picture. Offline checks and
Kivy component checks enforce correct visual controls and no implicit commands.
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


class ProductionVisualOffline(unittest.TestCase):
    def test_four_grade_labels_replace_unsupported_mockup_modes(self):
        source = (ROOT / "android_app/pages/production_visual.py").read_text("utf-8")
        engine = (ROOT / "wlre/services/items/alchemy.py").read_text("utf-8")
        production = (ROOT / "android_app/pages/production.py").read_text("utf-8")
        for text in (source, engine, production):
            ast.parse(text)
        for core, label in [
            ("無技能", "無煉金術"), ("一般", "初級煉金術"),
            ("中階", "中級煉金術"), ("高階", "高級煉金術"),
        ]:
            self.assertIn("('{}', '{}')".format(core, label), source)
            self.assertIn("'{}':".format(core), engine)
        self.assertIn("self.level_bar = AlchemyLevelBar(self._choose_level)", production)
        self.assertIn("core_mode not in modes(self.state)", production)
        self.assertIn("self.level_bar.set_available(options if not busy else ()", production)
        for unsupported in ("標準煉金", "批量煉金", "指定產物"):
            self.assertNotIn(unsupported, production)

    def test_visual_cards_are_actual_kivy_widgets_and_data_bound(self):
        source = (ROOT / "android_app/pages/production_visual.py").read_text("utf-8")
        production = (ROOT / "android_app/pages/production.py").read_text("utf-8")
        for cls in ("AlchemyLevelBar", "MaterialSlot", "RecipeRow",
                    "IngredientRow", "QueueEntry", "ProgressRail"):
            self.assertIn("class {}".format(cls), source)
        for token in ("tile = MaterialSlot(", "card = RecipeRow(",
                      "IngredientRow(", "QueueEntry(", "ProductionPanel("):
            self.assertIn(token, production)
        self.assertIn("recipe_plan(state, sid, number)", production)
        self.assertIn("prepare(state, command)", production)


@unittest.skipUnless(HAS_KIVY and (os.environ.get("DISPLAY") or os.name == "nt"),
                     "Kivy graphics display required")
class ProductionVisualKivy(unittest.TestCase):
    def fake_dashboard(self):
        out = []
        state = {
            "knowledge": {"player": {
                "ready": True, "skills": {
                    "15997": {"level": 1}, "15998": {"level": 1}}}},
            "inventory": {"ready": True, "items": {}},
            "alchemy": {}, "crafting": {"queue": {}}, "furniture": {},
        }
        d = SimpleNamespace(page_name="", state=state, live=False,
                            closed=False, data={"preferences": {
                                "favorites": [], "plan": []}},
                            message=SimpleNamespace(text=""),
                            send=lambda *args: out.append(args))
        return d, out

    def test_visual_grade_buttons_gate_unlearned_and_send_core_mode(self):
        from kivy.uix.widget import Widget
        from android_app.pages.production import Alchemy
        d, outgoing = self.fake_dashboard()
        with patch("android_app.pages.production.item_image",
                   side_effect=lambda *a, **kw: Widget(
                       size_hint=(None, None), size=(36, 36))), \
             patch("android_app.pages.production.item_name",
                   return_value="測試材料"):
            page = Alchemy(d, compact=True)
            page.refresh()
            controls = page.level_bar.buttons
            self.assertEqual(
                [controls[name].text for name in
                 ("無技能", "一般", "中階", "高階")],
                ["無煉金術", "初級煉金術", "中級煉金術", "高級煉金術"])
            self.assertFalse(controls["無技能"].disabled)
            self.assertFalse(controls["一般"].disabled)
            self.assertFalse(controls["中階"].disabled)
            self.assertTrue(controls["高階"].disabled)
            original = page.mode.text
            page._choose_level("高階")
            self.assertEqual(page.mode.text, original)
            page._choose_level("一般")
            self.assertEqual(page.mode.text, "一般")
            page.set_slot(0, {"index": 2, "item_id": 1001, "count": 1})
            with patch("android_app.pages.production.prepare",
                       return_value={"mode": "一般", "runs": 1,
                                     "consumption": [
                                         {"index": 2, "item_id": 1001,
                                          "count": 1}]}):
                command, _ = page._current_plan()
                self.assertEqual(command["mode"], "一般")
                page.preview_cost()
                self.assertEqual(outgoing, [])
            d.state["alchemy"]["enabled"] = True
            page.refresh()
            self.assertTrue(all(b.disabled for b in controls.values()))
            d.state["alchemy"]["enabled"] = False
            d.state["knowledge"]["player"]["skills"]["15999"] = {"level": 1}
            page.refresh()
            self.assertFalse(controls["高階"].disabled)

    def test_real_material_and_recipe_widgets_keep_verified_rows(self):
        from kivy.uix.widget import Widget
        from android_app.pages.production_visual import (
            MaterialSlot, RecipeRow, IngredientRow, QueueEntry)
        selected, dispatched = [], []
        with patch("android_app.pages.production_visual.item_image",
                   side_effect=lambda *a, **kw: Widget(
                       size_hint=(None, None), size=(36, 36))):
            slot = MaterialSlot(0, lambda: selected.append("pick"),
                                lambda: selected.append("remove"))
            self.assertTrue(slot.remove_button.disabled)
            slot.set_item({"index": 5, "item_id": 123}, "已核對材料")
            self.assertFalse(slot.remove_button.disabled)
            self.assertIn("格位 #5", slot.pick_button.text)
            self.assertEqual(slot.title.text, "已核對材料")
            recipe = {"item_id": 123}
            entry = RecipeRow(recipe, "測試配方", "設備待確認",
                              lambda r: selected.append(r["item_id"]))
            entry.dispatch("on_release")
            self.assertIn(123, selected)
            material = IngredientRow(
                {"item_id": 123, "name": "已確認物品",
                 "usable": None, "required": 5})
            self.assertTrue(any(
                getattr(child, "text", "") == "待同步"
                for child in material.children))
            queue = QueueEntry(
                123, "測試配方", 2, 1, "未知", None,
                lambda a, i: dispatched.append((a, i)))
            self.assertEqual(queue.progress.ratio, 0)
            self.assertEqual(dispatched, [])
            self.assertEqual(len(queue.children), 3)


if __name__ == "__main__":
    unittest.main()
