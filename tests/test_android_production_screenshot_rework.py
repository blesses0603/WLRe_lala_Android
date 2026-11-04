"""Regression for the user's real v7.1.15 Android screenshot feedback.

This is an operational/layout contract. It does not claim screenshot pixel
parity without the v7.1.16 APK and an actual device capture.
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
    def test_only_production_pair_has_flat_single_workbench(self):
        combined = (ROOT / "android_app/pages/combined.py").read_text("utf-8")
        general = (ROOT / "android_app/pages/general.py").read_text("utf-8")
        production = (ROOT / "android_app/pages/production.py").read_text("utf-8")
        for source in (combined, general, production):
            ast.parse(source)
        self.assertIn("class AlchemyAndCrafting(Page):", combined)
        self.assertIn("super().__init__(d, show_title=False)", combined)
        self.assertIn("self.workbench = BoxLayout(", combined)
        self.assertIn("self.select('煉金')", combined)
        self.assertIn("page_type(proxy, compact=True)", combined)
        self.assertIn("embedded=False, show_title=True", general)
        self.assertEqual(production.count("super().__init__(d, embedded=compact)"), 2)
        self.assertIn("row_default_height=dp(148)", production)
        self.assertIn("'cols', 2 if width < dp(245) else 3", production)
        self.assertIn("if compact:\n            # The original order buried", production)
        self.assertIn("self.add_widget(materials)", production)
        self.assertIn("self.add_widget(setup)", production)

    def test_no_server_command_is_added_in_screen_wrapper(self):
        combined = (ROOT / "android_app/pages/combined.py").read_text("utf-8")
        block = combined.split("class AlchemyAndCrafting(Page):", 1)[1]
        self.assertNotIn(".send(", block)
        self.assertNotIn("game_command(", block)


@unittest.skipUnless(HAS_KIVY and (os.environ.get("DISPLAY") or os.name == "nt"),
                     "Requires Kivy and a graphical display")
class ScreenshotKivyLayout(unittest.TestCase):
    def test_workbench_has_one_active_controller_without_recreating_draft(self):
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
            # Controls, short status, and ONE workbench. No outer guide cards.
            self.assertEqual(len(view.children), 3)
            self.assertEqual(len(view.workbench.children), 1)
            self.assertEqual(view.active, "煉金")
            alchemy = view.sections["煉金"]["view"]
            self.assertIsInstance(alchemy, Alchemy)
            self.assertEqual(alchemy.material_grid.cols, 3)
            self.assertEqual(alchemy.material_grid.row_default_height, dp(148))
            self.assertEqual(len(alchemy.material_grid.children), 5)
            self.assertEqual(view.sections["製作工坊"]["view"], None)
            alchemy.slots[0][1].text = "7"
            alchemy.runs.text = "9"

            view.select("製作工坊")
            self.assertEqual(view.active, "製作工坊")
            self.assertFalse(view.sections["煉金"]["expanded"])
            self.assertEqual(len(view.workbench.children), 1)
            self.assertTrue(view.sections["製作工坊"]["view"].compact)
            view.select("煉金")
            self.assertIs(view.sections["煉金"]["view"], alchemy)
            self.assertEqual(alchemy.slots[0][1].text, "7")
            self.assertEqual(alchemy.runs.text, "9")
            self.assertEqual(len(view.workbench.children), 1)
            self.assertEqual(sent, [])
            view.close()


if __name__ == "__main__":
    unittest.main()
