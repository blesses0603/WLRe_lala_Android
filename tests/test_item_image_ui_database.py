import io,os,unittest
from types import SimpleNamespace
from unittest.mock import patch
from PIL import Image

@unittest.skipUnless(os.environ.get('DISPLAY'),'Kivy display required')
class ItemImageUI(unittest.TestCase):
    def test_existing_widgets_switch_versions_and_clear_on_cold_runtime(self):
        from kivy.core.window import Window
        from android_app import assets
        def catalog(key,color):
            stream=io.BytesIO();Image.new('RGBA',(8,8),color).save(stream,format='PNG')
            return SimpleNamespace(catalog_key=key,icon=lambda sid:1000,png=lambda sid:stream.getvalue())
        runtime=SimpleNamespace(item_images=catalog('a','red'))
        with patch('wlre.services.world.dynamic_bundle_runtime.current_runtime',return_value=runtime),patch.dict(assets._CACHE,{},clear=True):
            widget=assets.item_image(79)
            self.assertEqual(widget.texture.pixels[:4],bytes([255,0,0,255]))
            runtime.item_images=catalog('b','blue')
            # Another consumer may populate the texture cache before the refresh.
            assets.item_texture(80)
            assets._refresh_item_widgets(0)
            self.assertEqual(widget.texture.pixels[:4],bytes([0,0,255,255]))
            runtime.item_images=None;assets._refresh_item_widgets(0)
            self.assertIsNone(widget.texture)
