"""Android v7.1.14 map zoom and inline bag detail UI regression."""
import ast
import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import unittest

ROOT = Path(__file__).resolve().parents[1]
HAS_KIVY = importlib.util.find_spec('kivy') is not None


class OfflineMapBagParity(unittest.TestCase):
    def test_map_keeps_original_server_commands_and_only_crops_artwork(self):
        source=(ROOT/'android_app/pages/map.py').read_text('utf-8')
        ast.parse(source)
        for expected in ("ZOOM_LEVELS = (1.0, 1.5, 2.0, 3.0)",
                         "def viewport(self):", "def source_point(self, x, y):",
                         "tex_coords=(u0,v0,u1,v0,u1,v1,u0,v1)",
                         "def center_on_player(self):",
                         "def locate_player(self):",
                         "type='walk'", "type='portal_walk'",
                         "type='portal_direct'", "'type':'stop_walk'"):
            self.assertIn(expected,source)
        self.assertNotIn("teleport_to_coordinate",source)

    def test_bag_selection_remains_server_backed_and_respects_read_only(self):
        source=(ROOT/'android_app/pages/resources.py').read_text('utf-8')
        ast.parse(source)
        for expected in ("def _sync_selected_panel(self, inventory, read_only):",
                         "def _display_selected(self, info, read_only):",
                         "current.get('item_id') != record.get('item_id')",
                         "current.get('item_id') != item_id",
                         "'超空間袋唯讀' if read_only",
                         "self._render_chunk(self._render_generation)"):
            self.assertIn(expected,source)


@unittest.skipUnless(HAS_KIVY and (os.environ.get('DISPLAY') or os.name == 'nt'),
                     'Kivy display is required')
class LiveMapBagParity(unittest.TestCase):
    def test_zoom_preserves_projection_and_clamps_focus(self):
        from android_app.pages.map import MapCanvas, ZOOM_LEVELS
        self.assertEqual(len(ZOOM_LEVELS),4)
        widget=MapCanvas(lambda *_:None)
        widget.pos=(0,0)
        widget.size=(320,320)
        self.assertEqual(widget.viewport(),(0,0,1024))
        widget.set_zoom(2.0)
        self.assertEqual(widget.viewport(),(256,256,512))
        self.assertEqual(widget.source_point(160,160),(512,512))
        widget.focus=(20,20)
        self.assertEqual(widget.viewport(),(0,0,512))
        for u,v in [(0,0),(100,200),(511,511)]:
            sx,sy=widget.screen(u,v)
            rx,ry=widget.source_point(sx,sy)
            self.assertAlmostEqual(rx,u)
            self.assertAlmostEqual(ry,v)
        with self.assertRaises(ValueError):
            widget.set_zoom(4.0)

        class Projection:
            def packet_to_pixel(self,x,y):
                return x*2,y*2
        widget.projection=Projection()
        widget.player={'x':400,'y':300}
        self.assertTrue(widget.center_on_player())
        self.assertEqual(widget.focus,(800,600))
        widget.player=None
        self.assertFalse(widget.center_on_player())

    def test_bag_details_follow_selected_item_and_clear_stale_data(self):
        from kivy.uix.widget import Widget
        from android_app.pages.resources import Resources
        inventory={'ready':True,'reliable':True,
                   'items':{'1':{'item_id':10,'count':2}}}
        state={'inventory':inventory}
        app=SimpleNamespace(state=state,page_name='包包與特技',live=False,
                            message=SimpleNamespace(text=''))
        def info(source,index,record):
            return {'id':record['item_id'],'name':'測試道具',
                    'index':int(index),'count':record['count'],
                    'available':record['count'],'reserved':0,
                    'effects':{'hp':10},'lines':['HP +10']}
        with patch('android_app.pages.resources.visible_items',
                   return_value=[('1',inventory['items']['1'],'測試道具')]), \
             patch('android_app.pages.resources.prefetch_item_icons'), \
             patch('android_app.pages.resources.item_image',
                   side_effect=lambda *_a,**_k:Widget()), \
             patch('android_app.pages.resources.item_details',
                   side_effect=info), \
             patch('android_app.pages.resources.dialog',
                   return_value=SimpleNamespace(dismiss=lambda:None)):
            page=Resources(app)
            page.refresh()
            page.show_item('1',{'item_id':10,'count':2})
            self.assertIn('HP +10',page.selected_details.text)
            self.assertIn('持有 2',page.selected_info.text)
            self.assertEqual(len(page.selected_preview.children),1)
            # Refresh reads the current server state and invalidates old slots.
            inventory['items']['1']={'item_id':11,'count':9}
            page.refresh()
            self.assertIsNone(page._selected_ref)
            self.assertEqual(len(page.selected_preview.children),0)
            # Remote storage is never displayed as a usable bag item.
            state['room_storage']={'garage':{'ready':True,'items':{
                '1':{'item_id':10,'count':4}}}}
            page.kind.text='超空間袋'
            page.show_item('1',{'item_id':10,'count':4})
            self.assertIn('超空間袋唯讀',page.selected_details.text)
            page.close()


if __name__ == '__main__':
    unittest.main()
