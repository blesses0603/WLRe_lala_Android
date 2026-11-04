"""Regression for bounded bag/skill rendering and batched icon archive reads."""
import ast
import importlib.util
import io
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
HAS_KIVY = importlib.util.find_spec("kivy") is not None


class BagLoadOffline(unittest.TestCase):
    def test_bag_refresh_does_not_stringify_unrelated_world_state(self):
        source = (ROOT / "android_app/pages/resources.py").read_text("utf-8")
        assets = (ROOT / "android_app/assets.py").read_text("utf-8")
        ast.parse(source)
        ast.parse(assets)
        for token in ("ITEM_RENDER_BATCH = 6",
                      "def _view_key(self, state, inventory):",
                      "if self.kind.text in ('包包', '超空間袋'):",
                      "Clock.schedule_once(", "self._cancel_render()",
                      "prefetch_item_icons(", "if key == self.key:"):
            self.assertIn(token, source)
        self.assertIn("with zipfile.ZipFile(", assets)
        self.assertIn("def prefetch_item_icons(item_ids):", assets)
        for token in ("current.get('item_id') != record.get('item_id')",
                      "read_only", "self.d.live", "learned_command"):
            self.assertIn(token, source)


@unittest.skipUnless(HAS_KIVY and (os.environ.get("DISPLAY") or os.name == "nt"),
                     "Requires Kivy with graphical display")
class BagLoadLive(unittest.TestCase):
    def test_prefetch_decodes_distinct_items_with_one_zip_read(self):
        from android_app import assets
        memory = io.BytesIO()
        with zipfile.ZipFile(memory, "w") as writer:
            writer.writestr("a.png", b"a")
            writer.writestr("b.png", b"b")
            writer.writestr("s1000.png", b"default")
        with patch.dict(assets._CACHE, {}, clear=True), \
             patch("android_app.assets._item_entry",
                   side_effect=lambda sid: {1: "a.png", 2: "b.png"}[sid]), \
             patch("wlre.storage.bundled_database.load_bundled_bytes",
                   return_value=memory.getvalue()) as loader, \
             patch("android_app.assets.CoreImage",
                   side_effect=lambda value, ext: SimpleNamespace(
                       texture=value.getvalue())) as image:
            self.assertEqual(assets.prefetch_item_icons([1, 2, 1]), 2)
            self.assertEqual(loader.call_count, 1)
            self.assertEqual(image.call_count, 2)
            self.assertEqual(assets.prefetch_item_icons([2, 1]), 0)
            self.assertEqual(loader.call_count, 1)

    def test_bag_builds_in_chunks_and_ignores_unrelated_state(self):
        from kivy.uix.widget import Widget
        from android_app.pages.resources import Resources, ITEM_RENDER_BATCH
        state = {"inventory": {"ready": True, "reliable": True,
                 "items": {str(n): {"item_id": n + 1, "count": n}
                           for n in range(24)}}}
        fake = SimpleNamespace(state=state, page_name="包包與特技",
                               live=False, message=SimpleNamespace(text=""))
        entries = [(str(n), state["inventory"]["items"][str(n)], "道具")
                   for n in range(24)]
        with patch("android_app.pages.resources.visible_items",
                   side_effect=lambda inventory, query: entries), \
             patch("android_app.pages.resources.prefetch_item_icons"), \
             patch("android_app.pages.resources.item_image",
                   side_effect=lambda *_a, **_k: Widget(size_hint=(None, None),
                                                         size=(64, 64))):
            page = Resources(fake)
            page.refresh()
            self.assertEqual(len(page.grid.children), ITEM_RENDER_BATCH)
            self.assertIsNotNone(page._render_event)
            generation = page._render_generation
            # A chat/world update does not invalidate the bag image grid.
            state["knowledge"] = {"unrelated": "frequent service update"}
            page.refresh()
            self.assertEqual(page._render_generation, generation)
            self.assertEqual(len(page.grid.children), ITEM_RENDER_BATCH)
            # Any in-place item count change must still rebuild the page.
            state["inventory"]["items"]["0"]["count"] = 99
            page.refresh()
            self.assertGreater(page._render_generation, generation)
            self.assertEqual(len(page.grid.children), ITEM_RENDER_BATCH)
            # Old scheduled callbacks cannot append stale items.
            page._render_chunk(generation)
            self.assertEqual(len(page.grid.children), ITEM_RENDER_BATCH)
            # Drain the remaining batches without needing a running app.
            while page._render_index < len(page._pending_items):
                if page._render_event is not None:
                    page._render_event.cancel()
                    page._render_event = None
                page._render_chunk(page._render_generation)
            self.assertEqual(len(page.grid.children), 24)
            self.assertEqual(page._render_event, None)
            page.close()

    def test_skills_ignore_unrelated_knowledge_but_track_learned_updates(self):
        from android_app.pages.resources import Resources
        state = {"knowledge": {"player": {"skills": {"100": {"level": 1}}}},
                 "inventory": {"ready": False}}
        fake = SimpleNamespace(state=state, page_name="包包與特技",
                               live=False, message=SimpleNamespace(text=""))
        actor = {"name": "角色", "pid": 1}
        skill = {"id": 100, "name": "已確認測試特技", "level": 1,
                 "sp": 3, "reasons": [], "source": "learned"}
        with patch("android_app.pages.resources.actors", return_value=[actor]), \\
             patch("android_app.pages.resources.skill_rows", return_value=[skill]), \\
             patch("android_app.pages.resources.prefetch_item_icons"):
            page = Resources(fake)
            page.kind.text = "已確認特技"
            before = page._render_generation
            state["knowledge"]["unrelated_chat_log"] = ["這不應重新建置技能清單"]
            page.refresh()
            self.assertEqual(page._render_generation, before)
            state["knowledge"]["player"]["skills"]["100"]["level"] = 2
            page.refresh()
            self.assertGreater(page._render_generation, before)
            page.close()

    def test_offscreen_pause_cancels_pending_icon_jobs(self):
        from android_app.pages.resources import Resources
        state = {"inventory": {"ready": True,
                 "items": {str(n): {"item_id": 1, "count": n}
                           for n in range(24)}}}
        fake = SimpleNamespace(state=state, page_name="包包與特技",
                               live=False, message=SimpleNamespace(text=""))
        entries = [(str(n), state["inventory"]["items"][str(n)], "道具")
                   for n in range(24)]
        with patch("android_app.pages.resources.visible_items", return_value=entries), \\
             patch("android_app.pages.resources.prefetch_item_icons"), \\
             patch("android_app.pages.resources.item_image",
                   return_value=__import__("kivy.uix.widget", fromlist=["Widget"]).Widget()):
            page = Resources(fake)
            page.refresh()
            pending = page._render_generation
            self.assertIsNotNone(page._render_event)
            page.pause_render()
            self.assertIsNone(page._render_event)
            self.assertIsNone(page.key)
            page._render_chunk(pending)
            self.assertEqual(len(page.grid.children), 6)
            page.close()
