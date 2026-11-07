import tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from emoji_fixtures import catalog
class EmojiUI(unittest.TestCase):
    def setUp(self):
        from kivy.core.window import Window
        self.assertIsNotNone(Window)
    def test_cold_start_current_png_same_key_update_and_invalidation(self):
        from android_app import assets
        with tempfile.TemporaryDirectory() as directory:
            runtime=SimpleNamespace(emoji_catalog=None,catalog_identity=SimpleNamespace(key='a'))
            with patch('wlre.services.world.dynamic_bundle_runtime.current_runtime',return_value=runtime),patch('wlre.storage.bundled_database.load_bundled_bytes',side_effect=AssertionError('old')):
                self.assertIsNone(assets.emoji_texture(1))
                runtime.emoji_catalog=catalog(Path(directory)/'db');one=assets.emoji_texture(1);self.assertIsNotNone(one)
                runtime.emoji_catalog=catalog(Path(directory)/'db','b'*64,'green');two=assets.emoji_texture(1);self.assertIsNot(one,two)
                runtime.emoji_catalog=None;self.assertIsNone(assets.emoji_texture(1));self.assertFalse([key for key in assets._CACHE if key[0]=='official_emoji'])
    def test_quick_buttons_refresh_and_picker_closes_on_source_loss(self):
        from test_android_chat_party_reference_ui import LivePairedChatAndParty
        from android_app.pages.social import Chat
        with tempfile.TemporaryDirectory() as directory:
            runtime=SimpleNamespace(emoji_catalog=None,catalog_identity=SimpleNamespace(key='a'))
            with patch('wlre.services.world.dynamic_bundle_runtime.current_runtime',return_value=runtime):
                d,sent=LivePairedChatAndParty().fake();d.page_name='聊天訊息'
                chat=Chat(d);chat.refresh();self.assertEqual(len(chat.emoji_reactions.children),1)
                chat.text.text='draft'
                runtime.emoji_catalog=catalog(Path(directory)/'db');chat.refresh()
                self.assertEqual(len(chat.emoji_reactions.children),3)
                chat.emojis();popup=chat.emoji_popup
                runtime.emoji_catalog=None;chat.refresh()
                self.assertIsNone(chat.emoji_popup);self.assertEqual(len(chat.emoji_reactions.children),1)
                self.assertEqual(chat.text.text,'draft');self.assertEqual(sent,[])
                popup.dismiss()
