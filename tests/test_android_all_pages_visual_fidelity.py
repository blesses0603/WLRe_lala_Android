"""Regression contract for reference-style Android design on all 18 pages.

This validates shared real Kivy components and source usage, NOT phone-pixel
identity or official login, which still requires an actual ARM64 device.
"""
import ast
import importlib.util
import os
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


def source(path):
    return (ROOT / path).read_text('utf-8')


class OfflineContract(unittest.TestCase):
    def test_every_page_is_mapped_and_has_reference_icon(self):
        import android_app.dashboard as dashboard
        from android_app.ui_shell import PAGE_SYMBOLS, NAV_ROUTES, PAGE_GROUPS
        self.assertEqual(len(dashboard.PAGES), 18)
        self.assertEqual(set(PAGE_SYMBOLS), set(dashboard.PAGES))
        self.assertEqual(set(PAGE_GROUPS), set(dashboard.PAGES))
        self.assertEqual(len(NAV_ROUTES), 4)
        self.assertTrue(all(
            type(v) is str and 1 <= len(v) <= 3
            for v in PAGE_SYMBOLS.values()))

    def test_shared_neon_is_applied_everywhere(self):
        required = {
            'android_app/theme.py': (
                'def neon_surface(', 'view._lala_neon_parts',
                "view._lala_button_sheen"),
            'android_app/ui_shell.py': (
                'class BrandHeader(BoxLayout)', 'verification_castle.jpg',
                'verification_mascot.jpg', 'PAGE_SYMBOLS',
                'neon_surface(self, color=SURFACE',
                'symbol+', 'NavigationDock('),
            'android_app/pages/general.py': (
                'neon_surface(self, color=SURFACE', "feature_card('事件紀錄'",
                "feature_card('效率分析條件'"),
            'android_app/pages/ui_components.py': (
                'CARD_SYMBOLS', 'neon_surface(panel',
                'section_title(title, subtitle,',
                'def message_button('),
            'android_app/dashboard.py': (
                'neon_surface(BoxLayout(', 'NavigationDock(',
                'self.page.refresh()', 'self._refresh_policy.should_refresh('),
            'android_app/app.py': (
                'neon_surface(column(), radius=24, bright=True)',
                'neon_surface(BoxLayout(', '_build_verification_view('),
            'android_app/widgets.py': (
                'frame = neon_surface(', 'popup.open()', 'style_input(view)'),
            'android_app/pages/resources.py': (
                "feature_card('戰場陣形'", "feature_card('本回合行動'",
                'style_button(view, primary=self.target == key)'),
        }
        for path, terms in required.items():
            code = source(path)
            with self.subTest(path=path):
                ast.parse(code, filename=path)
                for term in terms:
                    self.assertIn(term, code)

    def test_advanced_cards_retained_from_prior_stages(self):
        cards = {
            'general.py': ('角色與場景', '帳篷活動'),
            'resources.py': ('道具與特技清單', '戰場陣形'),
            'map.py': ('小地圖與即時位置', '目標座標與移動'),
            'social.py': ('聊天訊息', '組隊管理'),
            'companions.py': ('夥伴出戰',),
            'attributes.py': ('角色能力',),
            'expedition.py': ('星之方舟／遠征狀態',),
            'instances.py': ('官方副本／協力資料',),
            'production.py': ('煉金設定', '製作工坊'),
            'npc.py': ('NPC 對話',),
            'storage.py': ('儲藏空間與操作',),
            'benefits.py': ('時間魔方',),
            'settings.py': ('AI 與戰後補給',),
        }
        for name, titles in cards.items():
            path='android_app/pages/'+name
            code=source(path)
            with self.subTest(page=name):
                ast.parse(code, filename=path)
                self.assertIn('feature_card(', code)
                for title in titles:
                    self.assertIn(title, code)
        self.assertEqual(len(cards), 13)

    def test_keep_no_animation_and_real_login_gate(self):
        theme=source('android_app/theme.py')
        shell=source('android_app/ui_shell.py')
        dashboard=source('android_app/dashboard.py')
        app=source('android_app/app.py')
        self.assertNotIn('Clock.schedule_interval', theme)
        self.assertNotIn('Clock.schedule_interval', shell)
        self.assertIn('if self._login_ready():', app)
        self.assertIn('verified_for_login(', app)
        self.assertIn('self._login_host.add_widget(self._verification_view)', app)
        self.assertIn('self._login_host.add_widget(self._login_view)', app)
        self.assertIn('self.views[name] = (page, scroll)', dashboard)
        self.assertIn("self._refresh_policy.should_refresh(", dashboard)
        self.assertNotIn('verify=False', theme)
        self.assertNotIn('假驗證成功', theme)

    def test_visual_assets_are_only_decoration(self):
        for name in ('verification_mascot.jpg','verification_castle.jpg'):
            file = ROOT / 'android_app/assets' / name
            self.assertTrue(file.is_file(), name)
            self.assertLess(file.stat().st_size, 16*1024)
            self.assertTrue(file.read_bytes().startswith(b'\xff\xd8\xff'))
        self.assertNotIn('1286', source('android_app/ui_shell.py'))
        self.assertNotIn('官方版本驗證成功', source('android_app/ui_shell.py'))


HAS_KIVY = importlib.util.find_spec('kivy') is not None


@unittest.skipUnless(HAS_KIVY and (os.environ.get('DISPLAY') or os.name == 'nt'),
                     'Needs Kivy with an Xvfb or desktop display')
class LiveKivyStyles(unittest.TestCase):
    def test_real_glow_card_and_pressable_button(self):
        from kivy.uix.button import Button
        from kivy.uix.boxlayout import BoxLayout
        from android_app.theme import neon_surface, style_button
        card=neon_surface(BoxLayout(),bright=True)
        self.assertTrue(hasattr(card,'_lala_neon_parts'))
        self.assertTrue(hasattr(card,'_lala_surface_colors'))
        actions=style_button(Button(text='查詢'),primary=True)
        self.assertTrue(hasattr(actions,'_lala_button_sheen'))
        self.assertEqual(actions._lala_button_variant,'primary')
        actions.disabled=True
        self.assertEqual(actions._lala_button_variant,'primary')

    def test_working_brand_and_all_four_routes(self):
        from android_app.ui_shell import BrandHeader, NavigationDock, NAV_ROUTES
        header=BrandHeader(subtitle='角色功能', verified=False)
        self.assertTrue(header.logo.source.endswith('verification_mascot.jpg'))
        self.assertIn('尚未通過',header.status.text)
        header.set_verified(True)
        self.assertIn('已驗證',header.status.text)
        header.set_verified(False)
        self.assertIn('尚未通過',header.status.text)
        targets=[]
        dock=NavigationDock(lambda page:targets.append(page))
        self.assertEqual(len(dock.buttons),4)
        self.assertTrue(hasattr(dock,'_lala_neon_parts'))
        for _,page in NAV_ROUTES:
            dock.buttons[page].dispatch('on_release')
        self.assertEqual(targets,[route for _,route in NAV_ROUTES])

    def test_original_feature_and_compressed_pages_still_build(self):
        from types import SimpleNamespace
        from android_app.pages.general import Page, Events, Efficiency
        from android_app.pages.ui_components import feature_card
        fake=SimpleNamespace(page_name='事件紀錄', data={'log':[]},
                             state={}, live=False)
        page=Page(fake)
        self.assertTrue(hasattr(page,'_lala_neon_parts'))
        card=feature_card('聊天訊息','已同步訊息')
        self.assertTrue(hasattr(card,'_lala_neon_parts'))
        events=Events(fake)
        events.refresh()
        self.assertIn('尚無事件紀錄',events.info.text)
        fake.page_name='經驗效率'
        efficiency=Efficiency(fake)
        self.assertIsNotNone(efficiency.subject)
        self.assertIsNotNone(efficiency.unit)


if __name__ == '__main__':
    unittest.main()
