"""Kivy map consumes current database PNGs and clears unavailable versions."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from PIL import Image
from wlre.services.world.smallmap_database import import_images,PREFIX

class AndroidMapDatabase(unittest.TestCase):
    def test_cold_start_database_image_update_and_failure_clear_texture(self):
        from android_app.pages.map import MapPage
        from wlre.storage.bundled_database import load_bundled_bytes
        def remaining(name,**kwargs):
            if name=='smallmaps.zip':raise AssertionError('must not read old ZIP')
            return load_bundled_bytes(name,**kwargs)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'images.sqlite3';asset=PREFIX+'SmallMap2D_123.png'
            def images(key,color):return import_images(path,key,{'test':color},(asset,),lambda:iter([(asset,Image.new('RGBA',(1024,1024),color))]))
            stage=dict(model_id=123,map_width=1000,map_height=1000,small_offset_x=12,small_offset_y=12)
            runtime=SimpleNamespace(revision=1296,catalog_identity=SimpleNamespace(key='a'),smallmaps=None,stages={7:stage},scene_names={})
            dashboard=SimpleNamespace(state={'player':{'scene':7}},page_name='地圖',send=Mock(),live=False)
            with patch('wlre.services.world.runtime_1275.active_runtime',return_value=runtime),patch(
                    'wlre.services.world.dynamic_bundle_runtime.current_runtime',return_value=runtime),patch(
                    'android_app.pages.map.Portals',return_value=SimpleNamespace()),patch(
                    'android_app.pages.map.allowed_rows',return_value=[]),patch(
                    'wlre.storage.bundled_database.load_bundled_bytes',side_effect=remaining):
                page=MapPage(dashboard);page.refresh()
                self.assertIsNone(page.image.texture);self.assertIsNone(page.image.projection)
                runtime.smallmaps=images('a','blue');page.refresh()
                self.assertEqual(page.image.texture.size,(1024,1024))
                first=page.image.texture;old_rate=page.image.projection.rate
                runtime.catalog_identity.key='b';runtime.smallmaps=images('b','green');stage['map_width']=2000
                page.refresh()
                self.assertIsNot(page.image.texture,first)
                self.assertNotEqual(page.image.projection.rate,old_rate)
                runtime.smallmaps=None;page.refresh()
                self.assertIsNone(page.image.texture);self.assertIsNone(page.image.projection)
                self.assertIsNone(page.image.selected)
                dashboard.send.assert_not_called()
