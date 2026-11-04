"""Android stage-two feature UI contract and regression tests."""
import ast
import importlib.util
import os
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PAGES = (
    'general', 'resources', 'map', 'social', 'companions', 'attributes',
)


def source(name):
    return (ROOT / 'android_app' / 'pages' / (name + '.py')).read_text('utf-8')


class StageTwoOfflineTests(unittest.TestCase):
    def test_all_rebuilt_pages_parse(self):
        for name in ('ui_components', *PAGES):
            with self.subTest(page=name):
                ast.parse(source(name))

    def test_all_seven_feature_views_have_real_neon_cards(self):
        for name in PAGES:
            with self.subTest(page=name):
                self.assertIn('feature_card(', source(name))
        self.assertIn("feature_card('角色與場景'", source('general'))
        self.assertIn("feature_card('包包／超空間袋／特技'", source('resources'))
        self.assertIn("feature_card('附近玩家'", source('social'))
        self.assertIn("feature_card('夥伴出戰'", source('companions'))
        self.assertIn("feature_card('角色能力'", source('attributes'))
        self.assertIn("'小地圖與即時位置'", source('map'))

    def test_original_commands_and_security_checks_are_kept(self):
        sources = {p: source(p) for p in PAGES}
        for command in ("type='automatic_flows'", "type='tent'"):
            self.assertIn(command, sources['general'])
        for gate in ("record.get('item_id') != item_id",
                     "self.d.live", "read_only", "learned_command",
                     "def _selected_snapshot(self):",
                     "fresh['available'] <= 0",
                     "food_command", "battle_guard"):
            self.assertIn(gate, sources['resources'])
        for command in ("type='walk'", "type='portal_walk'",
                        "type='portal_direct'", "'type':'stop_walk'"):
            self.assertIn(command, sources['map'])
        for operation in ("action='respond'", "action='leave'",
                          "action='flag'", "'kick', 'leader'"):
            # Some actions use dict(action=...) and others use literals.
            self.assertIn(operation.split('=')[-1].strip("'"),
                          sources['social'])
        for guard in ("request_id", "status == 'sent'",
                      "status == 'uncertain'", "pending_started",
                      "self.sent_text", "self.sent_quote"):
            self.assertIn(guard, sources['social'])
        for guard in ("problem(self.state", "self.d.live", "self.d.send(",
                      "companion_rows(self.state)"):
            self.assertIn(guard, sources['companions'])
        for guard in ("preview_block_reason(", "baseline(", "total <= 0",
                      "total > current['attribute_potential']",
                      "'baseline':current", "'type':'allocate_points'"):
            self.assertIn(guard, sources['attributes'])

    def test_no_synthetic_game_data_or_unbounded_map_paint(self):
        for name in PAGES:
            self.assertNotIn('lalaplayer01', source(name))
            self.assertNotIn('官方資源已驗證', source(name))
        self.assertIn('if signature==self._draw_signature:',
                      source('map'))
        self.assertIn('self._draw_signature=signature', source('map'))
        self.assertIn('if key == self.key:', source('resources'))
        self.assertIn('if signature==self._signature:', source('companions'))
        self.assertIn('if key != self.key:', source('social'))

    def test_attr_entry_preserves_all_five_server_owned_fields(self):
        from android_app.pages.attributes import ATTRIBUTES, attribute_lines
        self.assertEqual(len(ATTRIBUTES), 5)
        self.assertEqual({key for key, _ in ATTRIBUTES},
                         {'str', 'con', 'agi', 'int', 'wis'})
        self.assertIn('未同步', '\\n'.join(attribute_lines({})))
        state = {'knowledge': {'player': {
            'ready': True,
            'stats': {'str': 10, 'int': 8, 'con': 4, 'agi': 9,
                      'wis': 5, 'attribute_potential': 2}}}}
        text = '\\n'.join(attribute_lines(state))
        self.assertIn('力量 STR：10', text)
        self.assertIn('剩餘可配點：2', text)


HAS_KIVY = importlib.util.find_spec('kivy') is not None


@unittest.skipUnless(HAS_KIVY and (os.environ.get('DISPLAY') or os.name == 'nt'),
                     'Requires Kivy and desktop display')
class StageTwoLiveWidgetTests(unittest.TestCase):
    def test_feature_card_is_resizable_and_status_is_live(self):
        from kivy.metrics import dp
        from kivy.uix.boxlayout import BoxLayout
        from android_app.pages.ui_components import feature_card, status_line
        panel = feature_card('測試卡片', '以真實元件呈現')
        self.assertIsInstance(panel, BoxLayout)
        self.assertTrue(hasattr(panel, '_lala_surface_colors'))
        status = status_line('等待同步')
        panel.add_widget(status)
        status.text = '已取得角色狀態'
        self.assertEqual(status.text, '已取得角色狀態')
        self.assertGreaterEqual(panel.height, 0)

    def test_attribute_steppers_edit_only_unsubmitted_input(self):
        from types import SimpleNamespace
        from android_app.pages.attributes import Attributes
        state = {}
        sent = []
        fake = SimpleNamespace(
            state=state, page_name='角色能力', live=False,
            message=SimpleNamespace(text=''),
            send=lambda *args: sent.append(args),
        )
        panel = Attributes(fake)
        self.assertEqual(len(panel.inputs), 5)
        panel._step('str', 1)
        self.assertEqual(panel.inputs['str'].text, '1')
        panel._step('str', -1)
        panel._step('str', -1)
        self.assertEqual(panel.inputs['str'].text, '0')
        self.assertEqual(sent, [])
        panel.refresh()
        self.assertIn('等待', panel.stat_values['str'].text)

    def test_map_does_not_repaint_unchanged_canvas(self):
        from kivy.graphics import Canvas
        from android_app.pages.map import MapCanvas
        widget=MapCanvas(lambda *_:None)
        widget.size=(320,320)
        widget.draw()
        stamp=widget._draw_signature
        widget.draw()
        self.assertEqual(widget._draw_signature,stamp)
        widget.selected={'x':12,'y':30}
        widget.draw()
        self.assertNotEqual(widget._draw_signature,stamp)


if __name__ == '__main__':
    unittest.main()
