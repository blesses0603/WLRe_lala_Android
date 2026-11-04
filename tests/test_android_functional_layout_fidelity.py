"""Android functional layout parity: real values and existing commands only.

The reference screenshots define visual hierarchy, not game protocol support.
No fabricated HP, faith maximum, companion portrait, or success receipts.
"""
import ast
import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class OfflineLayoutParity(unittest.TestCase):
    def test_companion_cards_show_source_backed_hp_sp(self):
        source = (ROOT / "android_app/pages/companions.py").read_text("utf-8")
        ast.parse(source)
        for token in ("StatMeter('HP'", "StatMeter('SP'",
                      "hp_meter.set_value(item['hp'],item['max_hp'])",
                      "sp_meter.set_value(item['sp'],item['max_sp'])",
                      "problem(self.state", "self.d.send(",
                      "if signature==self._signature:"):
            self.assertIn(token, source)
        self.assertNotIn("lalaplayer", source)

    def test_attributes_retain_all_five_official_fields(self):
        source = (ROOT / "android_app/pages/attributes.py").read_text("utf-8")
        ast.parse(source)
        for token in ("stat.add_widget(draft)", "editor.add_widget(stat)",
                      "self.available.text", "attribute_potential",
                      "'type':'allocate_points'", "preview_block_reason("):
            self.assertIn(token, source)
        self.assertNotIn("lalaplayer", source)


HAS_KIVY = importlib.util.find_spec("kivy") is not None


@unittest.skipUnless(HAS_KIVY and (os.environ.get("DISPLAY") or os.name == "nt"),
                     "Requires Kivy and a graphical display")
class LiveLayoutParity(unittest.TestCase):
    def test_companion_bars_use_only_real_game_state(self):
        from android_app.pages.companions import Companions
        from android_app.pages.ui_components import StatMeter
        state = {"knowledge": {"companions_ready": True,
                 "active_npc_id": 42,
                 "companions": {"1": {"npc_id": 42, "name": "測試夥伴",
                    "stats": {"level": 8, "hp": 50, "max_hp": 100,
                              "sp": 12, "max_sp": 40}, "faith": 23}}}}
        sent = []
        fake = SimpleNamespace(state=state, live=True, page_name="夥伴出戰",
                               message=SimpleNamespace(text=""),
                               send=lambda *args: sent.append(args))
        with patch("android_app.pages.companions.problem", return_value=None):
            page = Companions(fake)
            page.refresh()
        def descendants(view):
            for child in view.children:
                yield child
                yield from descendants(child)
        meters = {m.name: m for m in descendants(page)
                  if isinstance(m, StatMeter)}
        self.assertAlmostEqual(meters["HP"].ratio, 0.5)
        self.assertAlmostEqual(meters["SP"].ratio, 0.3)
        self.assertIn("23", str([v.text for v in descendants(page)
                                if hasattr(v, "text")]))
        self.assertEqual(sent, [])
        state["knowledge"]["companions"]["1"]["stats"].pop("hp")
        with patch("android_app.pages.companions.problem", return_value=None):
            page.refresh()
        meters = {m.name: m for m in descendants(page)
                  if isinstance(m, StatMeter)}
        self.assertIn("等待", meters["HP"].caption.text)
        self.assertEqual(sent, [])

    def test_attribute_draft_is_not_a_server_command(self):
        from android_app.pages.attributes import Attributes
        state = {"knowledge": {"player": {"ready": True, "stats": {
            "str": 10, "con": 9, "agi": 8, "int": 7, "wis": 6,
            "attribute_potential": 4}}}}
        sent = []
        fake = SimpleNamespace(state=state, live=False,
                               page_name="角色能力",
                               message=SimpleNamespace(text=""),
                               send=lambda *args: sent.append(args))
        page = Attributes(fake)
        page.refresh()
        self.assertIn("4", page.available.text)
        self.assertEqual(len(page.inputs), 5)
        page._step("str", 1)
        self.assertEqual(page.inputs["str"].text, "1")
        self.assertEqual(sent, [])
        state["knowledge"]["player"]["ready"] = False
        page.refresh()
        self.assertIn("等待", page.available.text)


if __name__ == "__main__":
    unittest.main()
