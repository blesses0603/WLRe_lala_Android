"""Android-wide style contract: the same reference art and neon chrome everywhere.

This verifies shared renderer/controls rather than trusting one static mockup.
It intentionally does not claim pixel-perfect device screenshots.
"""
import ast
import importlib.util
import os
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PAGES = (
    '角色概況', '包包與特技', '小地圖', '戰場陣形', '聊天', '組隊',
    '夥伴出戰', '遠征', '副本資料', '角色能力', '煉金', '製作',
    '經驗效率', '事件紀錄', 'AI與補給設定', 'NPC', '儲藏存取', '福利',
)


class GlobalReferenceStyleTests(unittest.TestCase):
    def test_global_neon_components_compile_and_have_no_animation_tick(self):
        for p in ('android_app/theme.py', 'android_app/ui_shell.py',
                  'android_app/pages/ui_components.py'):
            ast.parse((ROOT / p).read_text('utf-8'), filename=p)
        theme = (ROOT / 'android_app/theme.py').read_text('utf-8')
        self.assertIn('view._lala_surface_highlight = shine', theme)
        self.assertIn('view._lala_button_glint_color = glint_color', theme)
        self.assertIn('def surface(view,', theme)
        self.assertIn('def style_input(view,', theme)
        self.assertIn('view.canvas.before.insert(0, group)', theme)
        self.assertNotIn('schedule_interval(', theme)

    def test_all_18_pages_keep_shared_components(self):
        dash = (ROOT / 'android_app/dashboard.py').read_text('utf-8')
        from ast import literal_eval
        tree = ast.parse(dash)
        declared = None
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == 'PAGES'
                for t in node.targets):
                declared = literal_eval(node.value)
                break
        self.assertEqual(declared, PAGES)
        card = (ROOT / 'android_app/pages/ui_components.py').read_text('utf-8')
        self.assertIn('surface(panel,', card)
        self.assertIn('panel.add_widget(section_title(title, subtitle))', card)
        shell = (ROOT / 'android_app/ui_shell.py').read_text('utf-8')
        self.assertIn('verification_castle.jpg', shell)
        self.assertIn("name = Label(text=title", shell)
        self.assertIn("mark = Label(text='◇'", shell)
        self.assertIn('NavigationDock(BoxLayout)', shell)

    def test_reference_castle_asset_is_not_a_network_image(self):
        from PIL import Image
        path = ROOT / 'android_app/assets/verification_castle.jpg'
        self.assertTrue(path.is_file())
        with Image.open(path) as art:
            art.verify()
        assert (ROOT / 'android_app/assets/app.png').is_file()
        code = (ROOT / 'android_app/ui_shell.py').read_text('utf-8')
        self.assertNotIn('http://', code)
        self.assertNotIn('https://', code)


HAS_KIVY = importlib.util.find_spec('kivy') is not None


@unittest.skipUnless(HAS_KIVY and (os.environ.get('DISPLAY') or os.name == 'nt'),
                     'Requires Kivy and desktop display')
class GlobalReferenceKivyTests(unittest.TestCase):
    def test_card_and_buttons_reuse_static_canvas_instead_of_rebuilding(self):
        from kivy.uix.button import Button
        from kivy.uix.boxlayout import BoxLayout
        from android_app.theme import SOFT, surface, style_button
        card = surface(BoxLayout())
        highlight = card._lala_surface_highlight
        surface(card, color=SOFT)
        self.assertIs(card._lala_surface_highlight, highlight)
        button = style_button(Button(text='確定'), primary=True)
        glint = button._lala_button_glint_color
        style_button(button, primary=False)
        self.assertIs(button._lala_button_glint_color, glint)

    def test_branding_and_navigation_are_shared_by_all_pages(self):
        from android_app.ui_shell import BrandHeader, NavigationDock, section_title
        name = BrandHeader(subtitle='角色功能', verified=False)
        self.assertIsNotNone(name._lala_castle_art)
        self.assertIn('尚未通過', name.status.text)
        name.set_verified(True)
        self.assertIn('已驗證', name.status.text)
        route = NavigationDock(lambda *_: None)
        self.assertEqual(len(route.buttons), 4)
        self.assertTrue(all('\n' in control.text for control in route.buttons.values()))
        title = section_title('包包與特技', '搜尋物品')
        self.assertEqual(len(title.children), 2)


if __name__ == '__main__':
    unittest.main()
