"""Android paired chat/party screenshot parity without fake game data.

Offline source contracts and Xvfb-backed Kivy interaction checks. The target
art's player roster, battle powers, portraits and server success states are
design samples only and must never enter the real UI as constants.
"""
import ast
import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]


def code(path):
    return (ROOT / path).read_text("utf-8")


class SocialScreenshotContracts(unittest.TestCase):
    def test_reuses_original_send_and_server_ack_paths(self):
        paired=code("android_app/pages/combined.py")
        social=code("android_app/pages/social.py")
        for path in ("android_app/pages/combined.py",
                     "android_app/pages/social.py",
                     "android_app/pages/social_visual.py",
                     "android_app/ui_shell.py", "android_app/dashboard.py"):
            ast.parse(code(path),filename=path)
        self.assertIn("class ChatAndParty(PairedFeatures)",paired)
        self.assertIn("self.expand('聊天訊息')",paired)
        self.assertIn("self.expand('組隊管理')",paired)
        self.assertIn("super().refresh()",paired)
        self.assertIn("section['view'].ack(receipt)",paired)
        self.assertIn("class Chat(Page)",social)
        self.assertIn("class Party(Page)",social)
        for word in ("self.request_id", "self.pending_started",
                     "self.quote", "self.sent_quote", "self.d.send(command)",
                     "self.act('invite'", "self.act('apply'",
                     "type='team'", "type='chat'"):
            self.assertIn(word,social)
        self.assertNotIn("self.d.send(",paired)

    def test_live_icons_replaces_missing_font_square(self):
        shell=code("android_app/ui_shell.py")
        visual=code("android_app/pages/social_visual.py")
        for symbol in ("home","layers","bars","grid","chat","users",
                       "send","megaphone","pin","invite","smile",
                       "refresh"):
            self.assertTrue(('\''+symbol+'\'' in visual) or ('"'+symbol+'"' in visual), symbol)
        self.assertIn("class SocialIcon(Widget)",visual)
        self.assertIn("class MessageTile(BoxLayout)",visual)
        self.assertIn("class NearbyTile(BoxLayout)",visual)
        self.assertIn("self.icons[page] = picture",shell)
        self.assertIn("line.add_widget(SocialIcon(vector,edge=28))",shell)
        self.assertNotIn("Clock.schedule_interval",visual)

    def test_no_fabricated_visual_mockup_data_or_commands(self):
        sources=code("android_app/pages/combined.py")+code(
            "android_app/pages/social.py")+code(
            "android_app/pages/social_visual.py")
        for prohibited in ("lalaplayer01","RiverMoon","WindLeaf",
                           "328 人","158K","162K","Lv.129",
                           "已送出 ✅","假驗證成功"):
            self.assertNotIn(prohibited,sources)
        for method in ("_build_compact", "_render_compact",
                       "_refresh_compact", "_change_compact_channel"):
            self.assertIn("def "+method+"(",sources)
        self.assertIn("if getattr(self, 'compact', False):",sources)

    def test_version_changed_only_android(self):
        self.assertIn('ANDROID_VERSION = "7.1.21"',
                      code("android_app/version.py"))
        self.assertIn("version = 7.1.21",code("buildozer.spec"))


HAS_KIVY = importlib.util.find_spec("kivy") is not None


@unittest.skipUnless(HAS_KIVY and (os.environ.get("DISPLAY") or os.name == "nt"),
                     "Needs Kivy with graphical context")
class LivePairedChatAndParty(unittest.TestCase):
    def fake(self):
        sent=[]
        d=SimpleNamespace(
            page_name="聊天＋組隊",
            live=True,closed=False,
            views={},
            message=SimpleNamespace(text=""),
            state={"player":{"role_id":101,"scene":23},
                   "party":{"status":"已同步","teams":{},
                            "enabled":True,
                            "requests":{"team_invite:77":{
                                "type":"team_invite","status":"pending",
                                "role_id":77}},
                            "nearby":{"77":{"name":"測試附近玩家",
                                             "role_id":77,"scene":23},
                                      "88":{"name":"其他場景玩家",
                                            "role_id":88,"scene":48}}}},
            data={"chat":[{"name":"測試玩家","role_id":77,
                            "channel":"世界","text":"測試聊天內容"},
                           {"name":"本機角色","role_id":101,
                            "channel":"隊伍","text":"同步隊伍訊息"}]},
            send=lambda *args: sent.append(args) or True,
        )
        return d,sent

    def test_real_chat_visible_party_lazy_then_both_open(self):
        from android_app.pages.combined import ChatAndParty
        from android_app.pages.social import Chat,Party
        from android_app.pages.social_visual import MessageTile
        d,sent=self.fake()
        view=ChatAndParty(d)
        self.assertIsInstance(view.sections["聊天訊息"]["view"],Chat)
        self.assertIsNone(view.sections["組隊管理"]["view"])
        chat=view.sections["聊天訊息"]["view"]
        self.assertTrue(chat.compact)
        chat.refresh()
        self.assertTrue(any(isinstance(item,MessageTile)
                            for item in chat.messages.children))
        self.assertEqual(len(sent),0)
        view.refresh()
        party=view.sections["組隊管理"]["view"]
        self.assertIsInstance(party,Party)
        self.assertTrue(party.compact)
        self.assertTrue(view.sections["組隊管理"]["expanded"])
        self.assertEqual(len(sent),0)
        view.close()

    def test_pending_receipt_and_compose_are_not_faked(self):
        from android_app.pages.combined import ChatAndParty
        d,sent=self.fake()
        view=ChatAndParty(d)
        chat=view.sections["聊天訊息"]["view"]
        chat.text.text="手動草稿"
        chat.filter.text="世界"
        self.assertEqual(chat.text.text,"手動草稿")
        self.assertEqual(len(sent),0)
        chat.channel.text="密語"
        self.assertFalse(chat.target.disabled)
        chat.channel.text="區域"
        self.assertTrue(chat.target.disabled)
        chat.pending=True
        chat.request_id="verified-request-id"
        chat.sent_text="手動草稿"
        chat.sent_quote=None
        chat.send_button.disabled=True
        view.chat_ack({"request_id":"unrelated","status":"sent",
                       "text":"手動草稿"})
        self.assertTrue(chat.pending)
        view.chat_ack({"request_id":"verified-request-id","status":"sent",
                       "text":"手動草稿"})
        self.assertFalse(chat.pending)
        self.assertEqual(chat.text.text,"")
        self.assertIn("不代表對方已讀",chat.delivery_status.text)
        self.assertEqual(len(sent),0)
        view.close()

    def test_party_renders_only_same_scene_and_manual_commands(self):
        from android_app.pages.combined import ChatAndParty
        d,sent=self.fake()
        view=ChatAndParty(d)
        view.expand("組隊管理")
        party=view.sections["組隊管理"]["view"]
        party.refresh()
        self.assertIn("1",party.party_tabs["附近玩家"].text)
        self.assertEqual(sent,[])
        party._select_party_tab("組隊申請")
        self.assertEqual(len(sent),0)
        party._select_party_tab("我的隊伍")
        self.assertEqual(len(sent),0)
        party.act("invite",77)
        self.assertEqual(sent[-1][0],
                         {"type":"team","action":"invite","role_id":77})
        view.close()


if __name__ == "__main__":
    unittest.main()
