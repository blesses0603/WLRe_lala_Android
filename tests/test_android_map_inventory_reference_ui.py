"""Android P2 UI parity: zoomed map geometry and safe inline item details.

Reference screenshots are layout guidance only; all commands and item values
must continue to come from the live snapshot and the verified catalog.
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


class OfflineMapBagParity(unittest.TestCase):
    def test_real_map_routing_and_local_zoom_are_separate(self):
        source = (ROOT / "android_app/pages/map.py").read_text("utf-8")
        ast.parse(source)
        for phrase in ("def bounds(self):", "def pixel_at(self,x,y):",
                       "def center_on(self,u,v):", "tex_coords=(",
                       "button('定位角色',self.focus_player)",
                       "button('顯示全圖',self.reset_view)",
                       "type='walk'", "type='portal_walk'",
                       "type='portal_direct'"):
            self.assertIn(phrase, source)

    def test_item_inline_detail_is_revalidated_and_read_only(self):
        source = (ROOT / "android_app/pages/resources.py").read_text("utf-8")
        ast.parse(source)
        for phrase in ("def _selected_snapshot(self):",
                       "def _revalidate_selected(self):",
                       "def open_selected_item(self):",
                       "self._selected_icon_id",
                       "self._selected_snapshot()",
                       "still_read_only or not self.d.live",
                       "fresh['available'] <= 0",
                       "self.use_item(dict(current, index=current_index))",
                       "self._cancel_render()", "prefetch_item_icons"):
            self.assertIn(phrase, source)


@unittest.skipUnless(HAS_KIVY and (os.environ.get("DISPLAY") or os.name == "nt"),
                     "Requires Kivy and graphical display")
class KivyMapBagParity(unittest.TestCase):
    def test_zoomed_touch_remains_inverse_of_original_coordinates(self):
        from android_app.pages.map import MapCanvas
        picks = []
        canvas = MapCanvas(lambda x, y: picks.append((x, y)))
        canvas.pos = (10, 20)
        canvas.size = (320, 320)
        with patch.object(canvas, "draw"):
            canvas.set_zoom(2.0)
            canvas.center_on(600, 400)
            u, v = canvas.screen(650, 350)
            back_u, back_v = canvas.pixel_at(u, v)
            self.assertAlmostEqual(back_u, 650, places=6)
            self.assertAlmostEqual(back_v, 350, places=6)
            # Touching the rendered tile never transmits a walk command.
            canvas.texture = object()
            canvas.projection = SimpleNamespace(
                pixel_to_packet=lambda px, py: (px, py))
            touch = SimpleNamespace(x=u, y=v)
            self.assertTrue(canvas.on_touch_down(touch))
            self.assertEqual(picks, [(650, 350)])
            canvas.center_on(10, 10)
            left, bottom, right, top = canvas.bounds()
            self.assertGreaterEqual(left, 0)
            self.assertGreaterEqual(bottom, 0)
            self.assertLessEqual(right, 1)
            self.assertLessEqual(top, 1)
            canvas.set_zoom(99)
            self.assertEqual(canvas.zoom, 3.0)
            canvas.reset_view()
            self.assertEqual(canvas.bounds(), (0, 0, 1, 1))
        self.assertIsNone(canvas.pixel_at(-200, -200))

    def test_bag_selection_updates_without_sending_and_clears_on_slot_change(self):
        from kivy.uix.widget import Widget
        from android_app.pages.resources import Resources
        state = {"inventory": {"ready": True, "reliable": True,
                 "items": {"0": {"item_id": 1001, "count": 3}}}}
        sent = []
        d = SimpleNamespace(
            state=state, page_name="包包與特技", live=True,
            message=SimpleNamespace(text=""),
            send=lambda *args: sent.append(args))
        def detail(inventory, index, record):
            return {"id": record["item_id"], "name": "測試道具",
                    "index": int(index), "count": record["count"],
                    "reserved": 0, "available": record["count"],
                    "effects": {"hp": 10}, "lines": ["HP +10"]}
        with patch("android_app.pages.resources.item_details", side_effect=detail), \
             patch("android_app.pages.resources.visible_items",
                   side_effect=lambda inventory, search: [
                       ("0", inventory["items"]["0"], "測試道具")]), \
             patch("android_app.pages.resources.prefetch_item_icons"), \
             patch("android_app.pages.resources.item_image",
                   side_effect=lambda *a, **kw: Widget(
                       size_hint=(None, None), size=(64, 64))):
            view = Resources(d)
            view.refresh()
            view.show_item("0", {"item_id": 1001})
            self.assertIn("持有 3", view.selected_info.text)
            self.assertIn("HP +10", view.selected_details.text)
            self.assertEqual(sent, [])
            state["inventory"]["items"]["0"]["count"] = 7
            view.refresh()
            self.assertIn("持有 7", view.selected_info.text)
            state["inventory"]["items"]["0"]["item_id"] = 1002
            view.refresh()
            self.assertTrue(view.selected_action.disabled)
            self.assertIsNone(view._selected_item)
            self.assertEqual(sent, [])
            view.close()

    def test_item_action_rechecks_slot_when_popup_is_open(self):
        from kivy.uix.widget import Widget
        from kivy.uix.button import Button
        from android_app.pages.resources import Resources
        state = {"inventory": {"ready": True, "reliable": True,
                 "items": {"0": {"item_id": 1001, "count": 2}}}}
        messages = []
        d = SimpleNamespace(state=state, page_name="包包與特技",
                            live=True, message=SimpleNamespace(text=""),
                            send=lambda *args: messages.append(args))
        def detail(inventory, index, record):
            return {"id": record["item_id"], "name": "測試道具",
                    "index": int(index), "count": record["count"],
                    "reserved": 0, "available": record["count"],
                    "effects": {"hp": 10}, "lines": ["HP +10"]}
        popup = SimpleNamespace(dismiss=lambda: None)
        bodies = []
        def fake_dialog(title, body, height):
            bodies.append(body)
            return popup
        with patch("android_app.pages.resources.item_details", side_effect=detail), \
             patch("android_app.pages.resources.visible_items",
                   side_effect=lambda inv, search: [
                       ("0", inv["items"]["0"], "測試道具")]), \
             patch("android_app.pages.resources.prefetch_item_icons"), \
             patch("android_app.pages.resources.item_image",
                   side_effect=lambda *a, **kw: Widget(
                       size_hint=(None, None), size=(64, 64))), \
             patch("android_app.pages.resources.dialog",
                   side_effect=fake_dialog):
            page = Resources(d)
            page.refresh()
            page.show_item("0", {"item_id": 1001})
            page.open_selected_item()
            actions = [w for w in bodies[0].walk()
                       if isinstance(w, Button)
                       and "使用已確認" in w.text]
            self.assertEqual(len(actions), 1)
            state["inventory"]["items"]["0"]["item_id"] = 1002
            actions[0].dispatch("on_release")
            self.assertIn("格位已更新", d.message.text)
            self.assertEqual(messages, [])
            page.close()


if __name__ == "__main__":
    unittest.main()
