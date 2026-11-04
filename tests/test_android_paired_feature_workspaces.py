"""Combined Android Kivy workflows: real screen controls, no duplicate core.

The paired views reuse existing pages and do not bypass server verification.
Standalone routes remain available for backwards-compatible navigation.
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
PAIRED = ("聊天＋組隊", "遠征＋副本", "煉金＋製作")
ORIGINAL = ("聊天", "組隊", "遠征", "副本資料", "煉金", "製作")


class PairedOfflineContract(unittest.TestCase):
    def test_all_six_original_pages_remain_mapped(self):
        code = (ROOT / "android_app/dashboard.py").read_text("utf-8")
        shell = (ROOT / "android_app/ui_shell.py").read_text("utf-8")
        paired = (ROOT / "android_app/pages/combined.py").read_text("utf-8")
        for source in (code, shell, paired):
            ast.parse(source)
        for name in ORIGINAL + PAIRED:
            self.assertIn("'{}'".format(name), code)
            self.assertIn("'{}'".format(name), shell)
        self.assertIn("'聊天＋組隊': ('combined', 'ChatAndParty')", code)
        self.assertIn("'遠征＋副本': ('combined', 'ExpeditionAndInstances')", code)
        self.assertIn("'煉金＋製作': ('combined', 'AlchemyAndCrafting')", code)
        self.assertIn("lambda name=title: self.toggle(name)", paired)
        self.assertIn("if compact else page_type(proxy)", paired)
        self.assertIn("getattr(module, cls_name)(proxy, compact=True)", paired)
        self.assertIn("section['slot'].remove_widget(view)", paired)
        self.assertIn("section['view'].refresh()", paired)

    def test_chat_ack_and_idle_refresh_cover_combined_route(self):
        dashboard = (ROOT / "android_app/dashboard.py").read_text("utf-8")
        policy = (ROOT / "android_app/refresh_policy.py").read_text("utf-8")
        self.assertIn("self.views['聊天＋組隊'][0].chat_ack(value)", dashboard)
        self.assertIn("('聊天', '聊天＋組隊')", dashboard)
        self.assertIn("'聊天＋組隊': 0.5", policy)
        self.assertIn("'遠征＋副本': 1.0", policy)
        self.assertIn("'煉金＋製作': 1.0", policy)
        combined = (ROOT / "android_app/pages/combined.py").read_text("utf-8")
        self.assertIn("'副本／協力'", combined)
        self.assertIn("section['view'].ack(receipt)", combined)
        self.assertNotIn("self.d.send(", combined)

    def test_original_protocol_guards_remain(self):
        original = {
            "social.py": ("request_id", "pending_started", "action='respond'"),
            "expedition.py": ("validate(", "self.d.send(", "available_quests("),
            "instances.py": ("confirm_cost=True", "if not self.d.live",
                             "instance_refresh", "instance_reward_claim"),
            "production.py": ("prepare(state, command)", "validate_rows(",
                              "confirmed_unlocked("),
        }
        for path, required in original.items():
            text = (ROOT / "android_app/pages" / path).read_text("utf-8")
            for token in required:
                with self.subTest(path=path, token=token):
                    self.assertIn(token, text)


@unittest.skipUnless(HAS_KIVY and (os.environ.get("DISPLAY") or os.name == "nt"),
                     "Kivy graphics context required")
class PairedKivyBehavior(unittest.TestCase):
    def fake_dashboard(self, name):
        sent = []
        obj = SimpleNamespace(page_name=name, data={"chat": []},
                              state={}, live=False, closed=False,
                              message=SimpleNamespace(text=""),
                              send=lambda *args: sent.append(args))
        return obj, sent

    def test_actual_chat_and_party_share_screen_and_preserve_draft(self):
        from android_app.pages.combined import ChatAndParty
        from android_app.pages.social import Chat, Party
        d, sent = self.fake_dashboard("聊天＋組隊")
        view = ChatAndParty(d)
        chat_part = view.sections["聊天訊息"]
        party_part = view.sections["組隊管理"]
        self.assertIsInstance(chat_part["view"], Chat)
        self.assertIsNone(party_part["view"])  # Expensive second panel is lazy.
        chat = chat_part["view"]
        chat.text.text = "已輸入但尚未發送"
        view.toggle("組隊管理")
        self.assertIsInstance(party_part["view"], Party)
        self.assertTrue(party_part["expanded"])
        view.toggle("聊天訊息")
        self.assertFalse(chat_part["expanded"])
        view.toggle("聊天訊息")
        self.assertIs(chat_part["view"], chat)
        self.assertEqual(chat.text.text, "已輸入但尚未發送")
        view.refresh()
        self.assertEqual(sent, [])
        view.close()

    def test_server_ack_is_delivered_to_paired_chat(self):
        from android_app.pages.combined import ChatAndParty
        d, sent = self.fake_dashboard("聊天＋組隊")
        view = ChatAndParty(d)
        chat = view.sections["聊天訊息"]["view"]
        chat.text.text = "收到測試"
        chat.pending = True
        chat.request_id = "verified-request-id"
        chat.sent_text = "收到測試"
        chat.sent_quote = None
        chat.send_button.disabled = True
        view.chat_ack({"request_id": "other", "status": "sent", "text": "收到測試"})
        self.assertTrue(chat.pending)
        view.chat_ack({"request_id": "verified-request-id",
                       "status": "sent", "text": "收到測試"})
        self.assertFalse(chat.pending)
        self.assertFalse(chat.send_button.disabled)
        self.assertEqual(chat.text.text, "")
        self.assertEqual(sent, [])
        view.close()

    def test_three_integrations_are_lazy_and_never_dispatch_on_expand(self):
        from kivy.metrics import dp
        from kivy.uix.boxlayout import BoxLayout
        from android_app.pages.combined import (
            ChatAndParty, ExpeditionAndInstances)

        class StubFeature(BoxLayout):
            def __init__(self, dashboard, compact=False):
                super().__init__(orientation="vertical",
                                 size_hint_y=None, height=dp(48))
                self.d = dashboard
                self.compact = compact
                self.refresh_count = 0
                self.close_count = 0

            def refresh(self):
                self.refresh_count += 1

            def close(self):
                self.close_count += 1

        modules = SimpleNamespace(
            Chat=StubFeature, Party=StubFeature,
            Expedition=StubFeature, InstanceCatalog=StubFeature,
            Alchemy=StubFeature, Crafting=StubFeature)
        cases = (
            (ChatAndParty, "聊天＋組隊", "聊天訊息", "組隊管理"),
            (ExpeditionAndInstances, "遠征＋副本",
             "星之方舟／遠征", "副本／協力"),
        )
        with patch("android_app.pages.combined.import_module",
                   return_value=modules):
            for page_class, name, first_name, second_name in cases:
                with self.subTest(name=name):
                    d, sent = self.fake_dashboard(name)
                    combined = page_class(d)
                    first = combined.sections[first_name]
                    second = combined.sections[second_name]
                    self.assertIsNotNone(first["view"])
                    self.assertIsNone(second["view"])
                    self.assertEqual(len(second["slot"].children), 0)
                    combined.toggle(second_name)
                    self.assertEqual(len(second["slot"].children), 1)
                    self.assertTrue(second["expanded"])
                    self.assertNotEqual(second["view"].d.page_name, name)
                    self.assertFalse(second["view"].compact)
                    if name == "遠征＋副本":
                        # Prevent standalone auto-room query in paired view.
                        self.assertNotEqual(second["view"].d.page_name, "副本資料")
                    original = second["view"]
                    # These two original pairs still collapse their sections.
                    combined.toggle(second_name)
                    combined.refresh()
                    self.assertFalse(second["expanded"])
                    combined.toggle(second_name)
                    self.assertIs(second["view"], original)
                    self.assertEqual(sent, [])
                    combined.close()
                    self.assertEqual(original.close_count, 1)


    def test_alchemy_and_crafting_are_both_visible_in_reference_layout(self):
        from kivy.uix.boxlayout import BoxLayout
        from android_app.pages.combined import AlchemyAndCrafting

        sent = []
        dashboard = SimpleNamespace(
            page_name="煉金＋製作", state={}, data={}, closed=False,
            live=False, message=SimpleNamespace(text=""),
            send=lambda *args: sent.append(args))

        class StubProduction(BoxLayout):
            def __init__(self, dashboard, compact=False):
                super().__init__(orientation="vertical", size_hint_y=None,
                                 height=48)
                self.d = dashboard
                self.compact = compact
                self.count = 0
                self.closes = 0
            def refresh(self):
                self.count += 1
            def close(self):
                self.closes += 1

        module = SimpleNamespace(Alchemy=StubProduction,
                                 Crafting=StubProduction)
        with patch("android_app.pages.combined.import_module",
                   return_value=module):
            view = AlchemyAndCrafting(dashboard)
            self.assertEqual(len(view.workbench.children), 2)
            for area in ("煉金", "製作工坊"):
                self.assertTrue(view.sections[area]["expanded"])
                self.assertTrue(view.sections[area]["view"].compact)
            before = [view.sections[a]["view"] for a in ("煉金", "製作工坊")]
            view.refresh()
            view.expand("製作工坊")
            self.assertEqual(
                before, [view.sections[a]["view"]
                         for a in ("煉金", "製作工坊")])
            self.assertEqual(sent, [])
            view.close()
            self.assertTrue(all(item.closes == 1 for item in before))


if __name__ == "__main__":
    unittest.main()
