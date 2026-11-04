"""Controller-composition contracts, runnable without an Android GL context.

The production class bodies run against a tiny layout adapter here; existing
feature-page tests own the actual protocol guards and Kivy rendering checks.
"""
import ast
import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace
import unittest


SOURCE = Path(__file__).resolve().parents[1] / 'android_app/pages/combined.py'


class Layout:
    def __init__(self, **kwargs):
        self.children = []
        self.__dict__.update(kwargs)

    def bind(self, **kwargs):
        pass

    def setter(self, name):
        return lambda _, value: setattr(self, name, value)

    def add_widget(self, child):
        if child in self.children:
            raise AssertionError('A retained view was attached twice')
        self.children.insert(0, child)

    def remove_widget(self, child):
        self.children.remove(child)


class Page(Layout):
    def __init__(self, dashboard, **kwargs):
        super().__init__(**kwargs)
        self.d = dashboard


class Controller(Page):
    def __init__(self, dashboard, **kwargs):
        super().__init__(dashboard)
        self.compact = kwargs.get("compact", False)
        self.refreshes = self.pauses = self.closes = 0
        self.draft = ''

    def refresh(self):
        self.refreshes += 1

    def pause_render(self):
        self.pauses += 1

    def close(self):
        self.closes += 1


def workspace_types():
    """Execute real workspace logic without importing Kivy or game catalogs."""
    loaded = []

    def import_module(name):
        loaded.append(name)
        return SimpleNamespace(**{key: Controller for key in (
            'Companions', 'Attributes', 'SettingsPage', 'NPC', 'Storage',
            'Benefits')})

    env = {
        'Page': Page, 'BoxLayout': Layout, 'dp': lambda value: value,
        'import_module': import_module,
        'feature_card': lambda *args, **kwargs: Layout(),
        'status_line': lambda text='': SimpleNamespace(text=text),
        'button': lambda text, callback, height: SimpleNamespace(
            text=text, callback=callback, height=height),
    }
    names = {'_SectionDashboard', 'PairedFeatures', '_ReferenceWorkspace',
             'CompanionsAndAttributes', 'SettingsAndTools'}
    tree = ast.parse(SOURCE.read_text('utf-8'))
    classes = ast.Module(body=[node for node in tree.body
                              if isinstance(node, ast.ClassDef)
                              and node.name in names], type_ignores=[])
    exec(compile(classes, str(SOURCE), 'exec'), env)
    return env, loaded


class ReferenceWorkspaceContracts(unittest.TestCase):
    def setUp(self):
        self.types, self.loaded = workspace_types()
        self.sent = []
        self.dashboard = SimpleNamespace(
            state={}, live=False, data={}, send=lambda *args: self.sent.append(args))

    def test_companions_and_attributes_visible_without_commands(self):
        view = self.types['CompanionsAndAttributes'](self.dashboard)
        self.assertEqual(list(view.sections), ['夥伴出戰', '角色能力'])
        for section in view.sections.values():
            self.assertTrue(section['expanded'])
            self.assertEqual(section['slot'].children, [section['view']])
            self.assertEqual(section['view'].refreshes, 1)
            self.assertEqual(section['view'].d.page_name, '')
        self.assertEqual(self.sent, [])

    def test_settings_load_only_settings_until_user_expands_tool(self):
        view = self.types['SettingsAndTools'](self.dashboard)
        self.assertEqual(self.loaded, ['android_app.pages.settings'])
        for title in ('NPC 互動與對話', '儲藏存取', '福利／魔方'):
            self.assertIsNone(view.sections[title]['view'])
        view.sections['儲藏存取']['toggle'].callback()
        self.assertEqual(self.loaded[-1], 'android_app.pages.storage')
        view.expand('儲藏存取')
        self.assertEqual(self.loaded.count('android_app.pages.storage'), 1)
        self.assertEqual(self.sent, [])

    def test_drafts_survive_collapse_and_only_open_tools_refresh(self):
        view = self.types['SettingsAndTools'](self.dashboard)
        view.expand('儲藏存取')
        tool = view.sections['儲藏存取']['view']
        tool.draft = '2'
        view.collapse('儲藏存取')
        self.assertEqual(tool.pauses, 1)
        view.refresh()
        self.assertEqual(tool.refreshes, 1)
        view.expand('儲藏存取')
        self.assertIs(view.sections['儲藏存取']['view'], tool)
        self.assertEqual(tool.draft, '2')
        self.assertEqual(tool.refreshes, 2)
        self.assertEqual(self.sent, [])

    def test_proxy_reads_latest_account_snapshot(self):
        view = self.types['CompanionsAndAttributes'](self.dashboard)
        proxy = view.sections['角色能力']['view'].d
        self.dashboard.state = {'knowledge': {'player': {'ready': True}}}
        self.dashboard.live = True
        self.assertIs(proxy.state, self.dashboard.state)
        self.assertTrue(proxy.live)
        proxy.send({'type': 'test'})
        self.assertEqual(self.sent, [({'type': 'test'},)])

    def test_pause_and_close_do_not_materialize_hidden_tools(self):
        view = self.types['SettingsAndTools'](self.dashboard)
        view.expand('福利／魔方')
        view.collapse('福利／魔方')
        view.pause_render()
        view.close()
        self.assertEqual(len(self.loaded), 2)
        for title in ('AI與補給設定', '福利／魔方'):
            self.assertEqual(view.sections[title]['view'].closes, 1)
        self.assertEqual(self.sent, [])

    def test_composition_does_not_add_commands_or_timers(self):
        tree = ast.parse(SOURCE.read_text('utf-8'))
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name in (
                    '_ReferenceWorkspace', 'CompanionsAndAttributes',
                    'SettingsAndTools'):
                for call in ast.walk(node):
                    if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute):
                        self.assertNotIn(call.func.attr, (
                            'send', 'schedule_interval', 'schedule_once'))


HAS_GRAPHICS = importlib.util.find_spec('kivy') is not None and (
    os.environ.get('DISPLAY') or os.environ.get('SDL_VIDEODRIVER') == 'offscreen'
    or os.name == 'nt')


def live_dashboard():
    sent = []
    dashboard = SimpleNamespace(
        page_name='', live=True, closed=False, views={}, sid='preview',
        app=SimpleNamespace(manager=SimpleNamespace(sessions={})),
        message=SimpleNamespace(text=''), data={},
        state={
            'phase': 'world_ready', 'player': {'role_id': 1, 'scene': 1},
            'knowledge': {
                'companions_ready': True, 'active_npc_id': 900001,
                'companions': {'1': {
                    'ready': True, 'npc_id': 900001, 'name': '測試夥伴',
                    'faith': 80,
                    'stats': {'level': 10, 'hp': 80, 'max_hp': 100,
                              'sp': 40, 'max_sp': 50}}},
                'player': {'ready': True, 'stats': {
                    'str': 10, 'con': 11, 'agi': 12, 'int': 13, 'wis': 14,
                    'attribute_potential': 5}}},
            'time_cube': {'ready': True, 'count': 1, 'enabled': False},
            'room_storage': {'status': '等待儲藏空間同步'}},
        send=lambda *args: sent.append(args) or True)
    return dashboard, sent


@unittest.skipUnless(HAS_GRAPHICS, 'Needs Kivy and a display or SDL offscreen')
class RealReferenceWorkspaces(unittest.TestCase):
    def test_attributes_draft_survives_real_refresh_and_reopen(self):
        from android_app.pages.combined import CompanionsAndAttributes
        from android_app.pages.attributes import Attributes
        from android_app.pages.companions import Companions
        d, sent = live_dashboard()
        view = CompanionsAndAttributes(d)
        editor = view.sections['角色能力']['view']
        self.assertIsInstance(editor, Attributes)
        self.assertIsInstance(view.sections['夥伴出戰']['view'], Companions)
        editor.inputs['str'].text = '3'
        view.collapse('角色能力')
        view.refresh()
        view.expand('角色能力')
        self.assertIs(view.sections['角色能力']['view'], editor)
        self.assertEqual(editor.inputs['str'].text, '3')
        d.state = {'knowledge': {'player': {'ready': True, 'stats': {
            'str': 20, 'attribute_potential': 9}}}}
        view.refresh()
        self.assertIn('20', editor.stat_values['str'].text)
        self.assertIn('9', editor.available.text)
        self.assertEqual(editor.inputs['str'].text, '3')
        view.pause_render()
        view.close()
        self.assertEqual(sent, [])

    def test_all_real_tools_expand_without_commands(self):
        from android_app.pages.combined import SettingsAndTools
        d, sent = live_dashboard()
        view = SettingsAndTools(d)
        for title in ('NPC 互動與對話', '儲藏存取', '福利／魔方'):
            self.assertIsNone(view.sections[title]['view'])
            self.assertEqual(view.sections[title]['slot'].height, 0)
            view.expand(title)
        storage = view.sections['儲藏存取']['view']
        storage.count.text = '7'
        for title in ('NPC 互動與對話', '儲藏存取', '福利／魔方'):
            view.collapse(title)
            view.expand(title)
        view.refresh()
        self.assertEqual(storage.count.text, '7')
        benefits = view.sections['福利／魔方']['view']
        self.assertFalse(benefits.auto.active)
        d.state = dict(d.state, time_cube={'enabled': True})
        view.refresh()
        self.assertTrue(benefits.auto.active)
        self.assertTrue(benefits.open_button.disabled)
        view.pause_render()
        view.close()
        self.assertEqual(sent, [])

    def test_compact_variants_preserve_original_actions_and_defaults(self):
        from unittest.mock import patch
        from android_app.pages.attributes import Attributes
        from android_app.pages.settings import SettingsPage, SettingsEditor
        from android_app.pages.combined import SettingsAndTools
        d, sent = live_dashboard()
        standalone = Attributes(d)
        editor = Attributes(d, compact=True)
        self.assertFalse(standalone.compact)
        self.assertTrue(editor.compact)
        self.assertEqual(set(editor.inputs), set(standalone.inputs))
        editor._step('str', 1)
        self.assertEqual(editor.inputs['str'].text, '1')
        self.assertEqual(sent, [])
        editor.allocate()
        self.assertEqual(sent[0][0]['type'], 'allocate_points')
        self.assertEqual(sent[0][0]['increments']['str'], 1)
        self.assertEqual(sent[0][0]['baseline']['attribute_potential'], 5)
        self.assertTrue(sent[0][1])  # Same explicit confirmation text.
        self.assertFalse(SettingsPage(d).compact)
        hub = SettingsAndTools(d).sections['AI與補給設定']['view']
        self.assertTrue(hub.compact)
        self.assertEqual(tuple(hub.setting_buttons), SettingsEditor.TABS)
        with patch('android_app.pages.settings.SettingsEditor') as open_editor:
            hub.setting_buttons['一般設定'].dispatch('on_release')
            open_editor.assert_not_called()
            self.assertIn('等待', d.message.text)
            d.data = {'ai_settings': {}}
            for tab, control in hub.setting_buttons.items():
                control.dispatch('on_release')
                open_editor.assert_called_with(d.app, d.sid, tab)
            self.assertEqual(open_editor.call_count, 7)

    def test_real_layout_at_phone_widths(self):
        from kivy.clock import Clock
        from kivy.core.window import Window
        from android_app.pages.combined import (
            CompanionsAndAttributes, SettingsAndTools)
        for width in (320, 420):
            Window.size = (width, 800)
            for cls in (CompanionsAndAttributes, SettingsAndTools):
                d, sent = live_dashboard()
                view = cls(d)
                if cls is SettingsAndTools:
                    for title in ('NPC 互動與對話', '儲藏存取', '福利／魔方'):
                        view.expand(title)
                view.size_hint_x = None
                view.width = width
                Window.add_widget(view)
                try:
                    for _ in range(15):
                        Clock.tick()
                    for section in view.sections.values():
                        child = section['view']
                        if child is not None:
                            self.assertLessEqual(child.width, width)
                            self.assertGreater(child.height, 0)
                            if hasattr(child, 'inputs'):
                                for control in child.inputs.values():
                                    self.assertGreaterEqual(control.width, 44)
                    self.assertEqual(sent, [])
                finally:
                    Window.remove_widget(view)
                    view.close()


if __name__ == '__main__':
    unittest.main()
