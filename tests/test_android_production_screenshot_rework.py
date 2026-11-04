"""Screenshot-driven Android first-page parity contracts.

The supplied reference places alchemy above a simultaneous crafting
browser/detail and a visible server queue. These are layout/behavior tests,
not claims of image pixel parity or official-server success.
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


class ScreenshotStructureContract(unittest.TestCase):
    def test_alchemy_above_crafting_in_one_scrolling_workbench(self):
        combined = (ROOT / "android_app/pages/combined.py").read_text("utf-8")
        general = (ROOT / "android_app/pages/general.py").read_text("utf-8")
        production = (ROOT / "android_app/pages/production.py").read_text("utf-8")
        for source in (combined, general, production):
            ast.parse(source)
        self.assertIn("class AlchemyAndCrafting(Page):", combined)
        self.assertIn("super().__init__(d, show_title=False)", combined)
        self.assertIn("self.workbench = BoxLayout(", combined)
        self.assertIn("self.workbench.add_widget(view)", combined)
        self.assertIn("getattr(module, cls_name)(proxy, compact=True)", combined)
        self.assertNotIn("self.select('煉金')", combined)
        self.assertIn("embedded=False, show_title=True", general)
        self.assertEqual(
            production.count("super().__init__(d, embedded=compact)"), 2)
        self.assertIn("row_default_height=dp(156)", production)
        self.assertIn("2 if width < dp(245) else", production)
        self.assertIn("3 if width < dp(342) else 5", production)
        self.assertIn("workbench.add_widget(setup)", production)
        self.assertIn("workbench.add_widget(materials)", production)
        self.assertIn("workbench.add_widget(actions)", production)
        self.assertIn("self.crafting_panes = GridLayout(", production)
        self.assertIn("self.crafting_panes.add_widget(browse)", production)
        self.assertIn("self.crafting_panes.add_widget(preview)", production)
        self.assertIn("self.add_widget(execution)", production)

    def test_no_game_command_in_the_combined_layout_controller(self):
        combined = (ROOT / "android_app/pages/combined.py").read_text("utf-8")
        block = combined.split("class AlchemyAndCrafting(Page):", 1)[1]
        self.assertNotIn(".send(", block)
        self.assertNotIn("game_command(", block)


@unittest.skipUnless(HAS_KIVY and (os.environ.get("DISPLAY") or os.name == "nt"),
                     "Requires Kivy and a graphical display")
class ScreenshotKivyLayout(unittest.TestCase):
    def test_both_areas_render_without_hiding_local_material_draft(self):
        from kivy.metrics import dp
        from kivy.uix.boxlayout import BoxLayout
        from android_app.pages.combined import AlchemyAndCrafting
        from android_app.pages.production import Alchemy

        sent = []
        d = SimpleNamespace(
            page_name="煉金＋製作",
            state={"alchemy": {}, "inventory": {"ready": True, "items": {}},
                   "crafting": {"queue": {}}, "furniture": {}},
            data={"preferences": {"favorites": [], "plan": []}},
            live=False, closed=False, message=SimpleNamespace(text=""),
            send=lambda *args: sent.append(args))

        class StubCrafting(BoxLayout):
            def __init__(self, dashboard, compact=False):
                super().__init__(size_hint_y=None, height=dp(40))
                self.compact = compact
                self.d = dashboard
                self.refreshes = 0

            def refresh(self):
                self.refreshes += 1

        module = SimpleNamespace(Alchemy=Alchemy, Crafting=StubCrafting)
        with patch("android_app.pages.combined.import_module",
                   return_value=module), \
             patch("android_app.pages.production.modes",
                   return_value=["無技能"]):
            view = AlchemyAndCrafting(d)
            self.assertEqual(len(view.children), 1)  # one workbench, no tabs
            self.assertEqual(len(view.workbench.children), 2)
            alchemy = view.sections["煉金"]["view"]
            crafting = view.sections["製作工坊"]["view"]
            self.assertIsInstance(alchemy, Alchemy)
            self.assertIsInstance(crafting, StubCrafting)
            self.assertTrue(view.sections["煉金"]["expanded"])
            self.assertTrue(view.sections["製作工坊"]["expanded"])
            self.assertEqual(alchemy.material_grid.cols, 3)
            alchemy.material_grid.width = dp(380)
            self.assertEqual(alchemy.material_grid.cols, 5)
            self.assertEqual(alchemy.material_grid.row_default_height, dp(156))
            self.assertEqual(len(alchemy.material_grid.children), 5)
            self.assertEqual(len(alchemy.children), 1)  # one alchemy panel
            alchemy.slots[0][1].text = "7"
            alchemy.runs.text = "9"

            view.refresh()
            self.assertIs(view.sections["煉金"]["view"], alchemy)
            self.assertIs(view.sections["製作工坊"]["view"], crafting)
            self.assertEqual(alchemy.slots[0][1].text, "7")
            self.assertEqual(alchemy.runs.text, "9")
            self.assertGreater(crafting.refreshes, 0)
            self.assertEqual(sent, [])
            view.close()


if __name__ == "__main__":
    unittest.main()
