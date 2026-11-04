"""Reference navigation and small-phone header behavior, not APK acceptance."""
import ast
import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]


def constants(path):
    result = {}
    for node in ast.parse((ROOT / path).read_text('utf-8')).body:
        if isinstance(node, ast.Assign):
            try:
                value = ast.literal_eval(node.value)
            except (ValueError, TypeError):
                continue
            for target in node.targets:
                if isinstance(target, ast.Name):
                    result[target.id] = value
    return result


class ReferenceRoutes(unittest.TestCase):
    def test_reference_workspaces_and_original_routes_coexist(self):
        dashboard = constants('android_app/dashboard.py')
        shell = constants('android_app/ui_shell.py')
        self.assertEqual(set(dashboard['PAGES']), set(dashboard['_PAGE_IMPL']))
        self.assertEqual(set(dashboard['PAGES']), set(shell['PAGE_GROUPS']))
        self.assertEqual(set(dashboard['PAGES']), set(shell['PAGE_SYMBOLS']))
        self.assertEqual(dashboard['_PAGE_IMPL']['夥伴＋能力'],
                         ('combined', 'CompanionsAndAttributes'))
        self.assertEqual(dashboard['_PAGE_IMPL']['設定與工具'],
                         ('combined', 'SettingsAndTools'))
        self.assertEqual(dict(shell['NAV_ROUTES'])['工具箱'], '設定與工具')
        for name in ('夥伴出戰', '角色能力', 'AI與補給設定', 'NPC', '儲藏存取', '福利'):
            self.assertIn(name, dashboard['PAGES'])

    def test_tool_countdown_retains_one_second_refresh(self):
        from android_app.refresh_policy import RefreshPolicy
        policy = RefreshPolicy()
        self.assertTrue(policy.should_refresh('設定與工具', 1, True, 0))
        self.assertFalse(policy.should_refresh('設定與工具', 1, True, .5))
        self.assertTrue(policy.should_refresh('設定與工具', 1, True, 1))

    def test_recent_events_use_real_newlines_and_last_five(self):
        tree = ast.parse((ROOT / 'android_app/pages/general.py').read_text('utf-8'))
        overview = next(node for node in tree.body
                        if isinstance(node, ast.ClassDef) and node.name == 'Overview')
        refresh = next(node for node in overview.body
                       if isinstance(node, ast.FunctionDef) and node.name == 'refresh')
        assignment = next(node for node in ast.walk(refresh)
                          if isinstance(node, ast.Assign)
                          and isinstance(node.value, ast.BoolOp))
        namespace = {'self': SimpleNamespace(recent_events=SimpleNamespace(text='')),
                     'recent': ['event' + str(i) for i in range(7)]}
        exec(compile(ast.Module(body=[assignment], type_ignores=[]), '<events>', 'exec'), namespace)
        self.assertEqual(namespace['self'].recent_events.text,
                         '\n'.join(['event2', 'event3', 'event4', 'event5', 'event6']))


GRAPHICS = (importlib.util.find_spec('kivy') is not None
            and (os.environ.get('DISPLAY') or os.name == 'nt'
                 or os.environ.get('SDL_VIDEODRIVER') == 'offscreen'))


@unittest.skipUnless(GRAPHICS, 'Needs a Kivy graphics provider')
class ReferenceHeaderWidgets(unittest.TestCase):
    def test_narrow_and_wide_header_preserve_actions(self):
        from kivy.clock import Clock
        from kivy.metrics import dp
        from android_app.ui_shell import BrandHeader
        calls = []
        header = BrandHeader(subtitle='角色功能',
                             alerts=lambda: calls.append('events'),
                             settings=lambda: calls.append('settings'))
        for width in (320, 420, 600, 320):
            header.width = dp(width)
            header.do_layout()
            Clock.tick()
            self.assertEqual(header.actions.orientation,
                             'vertical' if width < 420 else 'horizontal')
            self.assertGreater(header.name_label.width, dp(150))
            self.assertEqual(len(header.actions.children), 2)
        for action in header.actions.children:
            action.dispatch('on_release')
        self.assertCountEqual(calls, ['settings', 'events'])
        self.assertIn('尚未通過', header.status.text)


if __name__ == '__main__':
    unittest.main()
