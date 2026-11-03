"""Static and functional contracts for Android-only neon redesign.

The suite runs without a Kivy display, alongside the existing optional real
Kivy widget tests and the full Python/Android CI gates.
"""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return (ROOT / path).read_text(encoding='utf-8')


def exported_tuple(path, name):
    tree = ast.parse(read(path), filename=path)
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
                return ast.literal_eval(node.value)
    raise AssertionError('Cannot find ' + name)


def contrast(first, second):
    def light(rgb):
        values = [(v / 12.92 if v <= .04045
                   else ((v + .055) / 1.055) ** 2.4)
                  for v in rgb[:3]]
        return .2126 * values[0] + .7152 * values[1] + .0722 * values[2]
    hi, lo = sorted((light(first), light(second)), reverse=True)
    return (hi + .05) / (lo + .05)


class AndroidVisualRedesignTests(unittest.TestCase):
    def test_modified_kivy_sources_parse(self):
        for path in (
            'android_app/theme.py', 'android_app/widgets.py',
            'android_app/ui_shell.py', 'android_app/app.py',
            'android_app/dashboard.py',
        ):
            with self.subTest(file=path):
                ast.parse(read(path), filename=path)

    def test_neon_inputs_are_legible_for_chinese_ime(self):
        path = 'android_app/theme.py'
        for name in ('INPUT_FILL', 'FOCUS_FILL'):
            background = exported_tuple(path, name)
            self.assertGreaterEqual(
                contrast(background, exported_tuple(path, 'INPUT_TEXT')), 7.0)
            self.assertGreaterEqual(
                contrast(background, exported_tuple(path, 'INPUT_HINT')), 4.5)
        source = read(path)
        self.assertIn('under_existing=True', source)
        self.assertIn('view.canvas.before.insert(0, group)', source)
        self.assertIn('view._lala_input_glyph_color', source)
        self.assertIn('view.bind(text=update_text_tint', source)

    def test_dock_routes_to_existing_pages(self):
        routes = exported_tuple('android_app/ui_shell.py', 'NAV_ROUTES')
        pages = exported_tuple('android_app/dashboard.py', 'PAGES')
        self.assertEqual(len(pages), 18)
        self.assertEqual(
            [name for name, _ in routes],
            ['首頁', '資料／資源', '運行紀錄', '工具箱'])
        self.assertEqual(len(set(v for _, v in routes)), 4)
        self.assertTrue(all(page in pages for _, page in routes))
        source = read('android_app/dashboard.py')
        self.assertIn('NavigationDock(', source)
        self.assertIn('self.dock.set_active(name)', source)
        self.assertIn('values=PAGES', source)
        self.assertIn('self.page.refresh()', source)
        self.assertIn('self._refresh_policy.should_refresh(', source)

    def test_verified_badges_are_not_fake_success_states(self):
        source = read('android_app/ui_shell.py')
        self.assertIn("verified = verified is True", source)
        self.assertIn('○ 官方資源尚未通過驗證', source)
        self.assertIn('● 官方資源已驗證', source)
        gate = read('android_app/app.py')
        self.assertIn('if self._login_ready():', gate)
        self.assertIn('self._login_brand_header.set_verified(True)', gate)
        self.assertIn('self._login_host.add_widget(self._verification_view)', gate)
        self.assertIn('self._login_host.add_widget(self._login_view)', gate)
        self.assertIn('not connected or service.get(\'status\') == \'checking\'', gate)
        # No successful verification version number may be hard-coded in a
        # UI mockup; production version numbers come from the real service.
        self.assertNotIn('DataPackage 1286 / MainPackage 1284', gate)
        self.assertNotIn('lalaplayer01', gate)

    def test_dialogs_and_controls_remain_interactive(self):
        widgets = read('android_app/widgets.py')
        self.assertIn('popup.open()', widgets)
        self.assertIn('frame.add_widget(section_title(title))', widgets)
        self.assertIn('view.bind(on_release=lambda *_: callback())', widgets)
        shell = read('android_app/ui_shell.py')
        self.assertIn('view.bind(on_release=lambda _button, target=page: navigate(target))', shell)
        self.assertIn('view._lala_button_refresh', read('android_app/theme.py'))
        self.assertNotIn('verify=False', shell)


if __name__ == '__main__':
    unittest.main()
