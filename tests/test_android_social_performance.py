"""Android v7.1.21 social performance and geometry regression contracts.

No game-server calls or fake success state. Kivy tests need Xvfb/graphics;
offline source tests ensure versioning and safe command boundaries.
"""
import ast
import importlib.util
import io
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from zipfile import ZipFile

ROOT=Path(__file__).resolve().parents[1]


def source(path):
    return (ROOT/path).read_text(encoding="utf-8")


class OfflineSocialPerformance(unittest.TestCase):
    def test_icon_geometry_is_immutable_after_setup(self):
        code=source("android_app/pages/social_visual.py")
        ast.parse(code)
        self.assertIn("PushMatrix()",code)
        self.assertIn("PopMatrix()",code)
        self.assertIn("Translate()",code)
        self.assertIn("Scale()",code)
        self.assertIn("self._tone.rgba = tint",code)
        self.assertIn("self.bind(pos=self._sync_geometry, size=self._sync_geometry)",code)
        self.assertNotIn("canvas.before.clear()",code)
        self.assertNotIn("self.bind(size=self._paint",code)
        self.assertIn("thick=1.10",code)

    def test_only_dashboard_owns_social_vertical_scroll(self):
        social=source("android_app/pages/social.py")
        dashboard=source("android_app/dashboard.py")
        for text in (social,dashboard):
            ast.parse(text)
        self.assertIn("self.message_scroll=BoxLayout(",social)
        self.assertIn("board.add_widget(self.entries)",social)
        self.assertNotIn("self.message_scroll=ScrollView(",social)
        self.assertNotIn("self.scroll=ScrollView(",social)
        self.assertIn("scroll = ScrollView(do_scroll_x=False)",dashboard)

    def test_emoji_zip_is_batched_not_reopened_per_button(self):
        assets=source("android_app/assets.py")
        social=source("android_app/pages/social.py")
        self.assertIn("def prefetch_emoji_textures(",assets)
        self.assertIn("sprites=prefetch_emoji_textures(keys)",social)
        self.assertIn("EmojiQuickButton(",social)
        self.assertNotIn("sprite=emoji_texture(key)",social)
        self.assertNotIn("setattr(icon,'center',w.center)",social)

    def test_dock_icon_and_caption_have_separate_areas(self):
        shell=source("android_app/ui_shell.py")
        self.assertIn("name = Label(text=title",shell)
        self.assertIn("icon.y = w.top - icon.height - dp(5)",shell)
        self.assertIn("caption.pos = (w.x + dp(2), w.y + dp(3))",shell)
        self.assertIn("size_hint_y=1",shell)
        self.assertNotIn("asset.pos=(w.center_x",shell)

    def test_only_real_game_operations_and_version(self):
        social=source("android_app/pages/social.py")
        self.assertIn("self.request_id = uuid.uuid4().hex",social)
        self.assertIn("if not self.pending or value.get('request_id')",social)
        self.assertIn("self.d.send(command)",social)
        self.assertNotIn("lalaplayer01",social)
        self.assertIn('ANDROID_VERSION = "7.1.21"',
                      source("android_app/version.py"))
        self.assertIn("version = 7.1.21",source("buildozer.spec"))


HAS_KIVY=importlib.util.find_spec("kivy") is not None


@unittest.skipUnless(HAS_KIVY and (os.environ.get("DISPLAY") or os.name=="nt"),
                     "Kivy graphical environment required")
class LiveSocialPerformance(unittest.TestCase):
    def test_icon_color_position_and_scale_do_not_rebuild_canvas(self):
        from android_app.pages.social_visual import SocialIcon
        icon=SocialIcon('chat',edge=22)
        original=tuple(icon.canvas.before.children)
        icon.pos=(20,30)
        icon.size=(42,42)
        icon.colorize((0.2,0.5,0.8,1))
        self.assertEqual(tuple(icon.canvas.before.children),original)
        self.assertAlmostEqual(icon._scale.x,42/24)
        self.assertAlmostEqual(icon._translate.x,20)
        self.assertEqual(tuple(icon._tone.rgba),(0.2,0.5,0.8,1))

    def test_dock_touches_remain_functional_without_overlap(self):
        from kivy.clock import Clock
        from android_app.ui_shell import NAV_ROUTES,NavigationDock
        calls=[]
        dock=NavigationDock(lambda target:calls.append(target))
        dock.pos=(0,0)
        dock.size=(320,60)
        for _ in range(2):
            Clock.tick()
        for _,route in NAV_ROUTES:
            button=dock.buttons[route]
            pic=dock.icons[route]
            label=dock.labels[route]
            self.assertGreaterEqual(pic.y,label.top)
            self.assertLessEqual(pic.top,button.top)
            self.assertGreaterEqual(label.y,button.y)
            button.dispatch("on_release")
        self.assertEqual(calls,[route for _,route in NAV_ROUTES])

    def test_unchanged_chat_snapshot_keeps_same_message_widgets(self):
        from android_app.pages.combined import ChatAndParty
        data={"chat":[{"role_id":77,"name":"測試玩家",
                      "channel":"世界","text":"文字一"}]}
        d=SimpleNamespace(page_name="聊天＋組隊",data=data,state={
            "player":{"role_id":1,"scene":5},
            "party":{"nearby":{},"requests":{},"teams":{},"status":"已同步"}},
            live=True,closed=False,message=SimpleNamespace(text=""),
            send=lambda *args:True,views={})
        pair=ChatAndParty(d)
        pair.refresh()
        chat=pair.sections["聊天訊息"]["view"]
        first=next(x for x in chat.messages.children
                   if x.__class__.__name__=="MessageTile")
        chat.refresh()
        chat.refresh()
        self.assertIn(first,chat.messages.children)
        self.assertEqual(sum(x.__class__.__name__=="MessageTile"
                             for x in chat.messages.children),1)
        pair.close()

    def test_batch_emoji_uses_current_database_and_deduplicates(self):
        from android_app import assets
        class FakeCore:
            def __init__(self,source,ext,**kwargs):self.texture=source.getvalue()
        with patch('wlre.services.world.emoji_database.source_token',return_value=('test',1)), patch('wlre.services.world.emoji_database.current_png',side_effect=lambda i: str(i).encode()) as read, patch('android_app.assets.CoreImage',FakeCore), patch('wlre.storage.bundled_database.load_bundled_bytes',side_effect=AssertionError('legacy')):
            result=assets.prefetch_emoji_textures([99101,99102,99101])
            self.assertEqual(len(result),2);self.assertEqual(read.call_count,2)
        for key in list(assets._CACHE):
            if key[0]=='official_emoji':assets._CACHE.pop(key)


if __name__=="__main__":
    unittest.main()
