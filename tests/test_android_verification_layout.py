"""Real Kivy geometry and gate contracts for the resource-entry UI preview."""
import importlib.util
import os
from pathlib import Path
import unittest
HAS_KIVY=importlib.util.find_spec('kivy') is not None
DISPLAY_OK=bool(os.environ.get('DISPLAY') or os.environ.get('SDL_VIDEODRIVER')=='offscreen' or os.name=='nt')

@unittest.skipUnless(HAS_KIVY and DISPLAY_OK,'Requires Kivy and a rendering backend')
class VerificationLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from kivy.core.text import LabelBase,DEFAULT_FONT
        font=Path(__file__).resolve().parents[1]/'android_app/assets/fonts/NotoSansTC-Regular.ttf'
        LabelBase.register(DEFAULT_FONT,fn_regular=str(font),fn_bold=str(font))

    def settle(self,panel):
        from kivy.clock import Clock
        for _ in range(12):
            Clock.tick()
            for widget in reversed(list(panel.walk())):
                layout=getattr(widget,'do_layout',None)
                if callable(layout):layout()

    def make_panel(self,width=393,height=852):
        from android_app.verification_ui import VerificationDashboard
        calls=[]
        panel=VerificationDashboard(lambda:calls.append('retry'),lambda:calls.append('service'),lambda:calls.append('enter'),size_hint=(None,None),size=(width,height))
        self.settle(panel)
        return panel,calls

    def test_bottom_actions_remain_visible_and_separate(self):
        for width,height in ((320,640),(360,780),(393,852),(430,932)):
            with self.subTest(width=width):
                panel,_=self.make_panel(width,height)
                self.assertAlmostEqual(panel.actions.y,panel.y)
                self.assertGreaterEqual(panel.viewport.y,panel.actions.top-1)
                self.assertAlmostEqual(panel.retry.y,panel.service_button.y)
                self.assertAlmostEqual(panel.retry.height,panel.service_button.height)
                self.assertLess(panel.retry.right,panel.service_button.x)
                self.assertGreaterEqual(panel.service_button.y,panel.enter_login.top)
                for button in (panel.retry,panel.service_button,panel.enter_login):
                    self.assertGreaterEqual(button.height,40)
                    self.assertGreaterEqual(button.x,panel.x)
                    self.assertLessEqual(button.right,panel.right)

    def test_row_text_and_versions_fit_at_large_font_scale(self):
        from kivy.metrics import Metrics
        old_scale=Metrics.fontscale
        try:
            Metrics.fontscale=1.3
            panel,_=self.make_panel(320,640)
            for row in panel.rows.values():
                self.assertGreaterEqual(row.name_label.height,row.name_label.texture_size[1])
                self.assertEqual(row.description.height,0)
                self.assertEqual(row.description.opacity,0)
                self.assertGreaterEqual(row.height,row.name_label.height+6)
                self.assertAlmostEqual(row.mark.center_y,row.center_y,delta=1)
            for label in panel.version_labels.values():
                self.assertGreaterEqual(label.height,label.texture_size[1])
        finally:Metrics.fontscale=old_scale

    def test_first_screen_fits_without_vertical_scroll(self):
        from kivy.metrics import Metrics
        from kivy.uix.scrollview import ScrollView
        old_scale=Metrics.fontscale
        try:
            for scale in (1.0,1.3):
                Metrics.fontscale=scale
                for width,height in ((320,640),(360,780),(393,852),(430,932)):
                    with self.subTest(width=width,height=height,font_scale=scale):
                        # The screenshot adds a 22px fixture banner outside the real UI.
                        panel,_=self.make_panel(width,height-22)
                        self.assertFalse(any(isinstance(w,ScrollView) for w in panel.walk()))
                        self.assertEqual(len(panel.rows),7)
                        for label in (panel.hero.headline,panel.hero.subtitle,panel.hero.badge,panel.inspection_title):
                            self.assertGreaterEqual(label.height,label.texture_size[1])
                        for widget in (panel.hero,panel.inspection,panel.versions,panel.result_card,*panel.rows.values()):
                            self.assertGreaterEqual(widget.y,panel.viewport.y-1)
                            self.assertLessEqual(widget.top,panel.viewport.top+1)
                        self.assertGreaterEqual(panel.hero.y,panel.inspection.top-1)
                        self.assertGreaterEqual(panel.inspection.y,panel.versions.top-1)
                        self.assertGreaterEqual(panel.versions.y,panel.result_card.top-1)
        finally:Metrics.fontscale=old_scale

    def test_complete_diagnostics_open_update_and_close(self):
        panel,_=self.make_panel(320,618)
        panel.apply_state({}, {},connected=False,detail='測試完整診斷資訊')
        popup=panel.open_details()
        self.assertIs(panel.open_details(),popup)
        self.assertIn('測試完整診斷資訊',panel._details_label.text)
        self.assertIn('檢查時間',panel._details_label.text)
        for row in panel.rows.values():
            self.assertIn(row.description.text,panel._details_label.text)
        panel.apply_state({'status':'blocked'}, {},connected=True,detail='更新後診斷資訊')
        self.assertIn('更新後診斷資訊',panel._details_label.text)
        self.assertNotIn('測試完整診斷資訊',panel._details_label.text)
        self.assertTrue(panel.enter_login.disabled)
        popup.dismiss(animation=False)
        self.assertIsNone(panel._details_popup)

    def test_images_do_not_grant_login_and_callbacks_remain_separate(self):
        panel,calls=self.make_panel()
        panel.apply_state({}, {}, connected=False,detail='等待同步')
        self.assertTrue(panel.enter_login.disabled)
        self.assertTrue(all(row._current=='pending' for row in panel.rows.values()))
        panel.retry.dispatch('on_release');panel.service_button.dispatch('on_release')
        self.assertEqual(calls,['retry','service'])
        token=[True,'a'*64]
        service={'status':'ready','ready':True,'catalog_token':token}
        local={'status':'ready','ready':True,'catalog_token':token}
        panel.apply_state(service,local,connected=True,login_ready=True,detail='已驗證')
        self.assertFalse(panel.enter_login.disabled)
        panel.enter_login.dispatch('on_release')
        self.assertEqual(calls,['retry','service','enter'])
        panel.apply_state(service,dict(local,catalog_token=[True,'b'*64]),connected=True,login_ready=True,detail='來源不一致')
        self.assertTrue(panel.enter_login.disabled)
        self.assertNotEqual(panel.rows['sqlite']._current,'passed')

    def test_only_checking_raster_animates_and_stops_cleanly(self):
        from kivy.uix.boxlayout import BoxLayout
        from kivy.core.window import Window
        from android_app.verification_ui import ReferenceGlyph
        panel,_=self.make_panel()
        host=BoxLayout();host.add_widget(panel)
        Window.add_widget(host)
        self.addCleanup(lambda:Window.remove_widget(host) if host in Window.children else None)
        panel.apply_state({'status':'checking'}, {},connected=True,detail='checking')
        icon=panel.rows['official'].state_icon
        self.assertIsInstance(icon,ReferenceGlyph)
        self.assertIsNotNone(icon._animation)
        self.assertTrue(all(r.state_icon._animation is None for k,r in panel.rows.items() if k!='official'))
        self.assertTrue(all(isinstance(b.glyph,ReferenceGlyph) and b.glyph._animation is None for b in (panel.retry,panel.service_button,panel.enter_login)))
        panel._pause_animation();self.assertIsNone(icon._animation)
        panel._resume_animation();self.assertIsNotNone(icon._animation)
        panel.apply_state({'status':'blocked'}, {},connected=True,detail='blocked')
        self.assertIsNone(icon._animation)
        panel.apply_state({'status':'checking'}, {},connected=True,detail='checking')
        self.assertIsNotNone(icon._animation)
        host.remove_widget(panel);self.assertIsNone(icon._animation)
        host.add_widget(panel);self.assertIsNotNone(icon._animation)
        Window.remove_widget(host);self.assertIsNone(icon._animation)
        Window.add_widget(host);self.assertIsNotNone(icon._animation)
        panel._stop_animation();self.assertIsNone(icon._animation)
        host.remove_widget(panel)

    def test_missing_decorations_do_not_block_the_gate(self):
        from unittest.mock import patch
        from android_app import verification_ui as ui
        with patch.object(ui,'_REFERENCE',None), patch.object(ui,'CoreImage',side_effect=RuntimeError('corrupt decoration')):
            panel=ui.VerificationDashboard(lambda:None,lambda:None)
            self.assertEqual(len(panel.rows),7)
            self.assertTrue(panel.enter_login.disabled)
            panel.apply_state({}, {},connected=False,detail='等待同步')
            self.assertTrue(panel.enter_login.disabled)

    def test_generated_panel_textures_have_reload_observer(self):
        from android_app.verification_ui import _gradient
        texture=_gradient((.051,.14,.22,1))
        self.assertEqual(texture.size,(1,32))
        self.assertIs(texture,_gradient((.051,.14,.22,1)))
        code=(Path(__file__).resolve().parents[1]/'android_app/verification_ui.py').read_text()
        self.assertIn('texture.add_reload_observer(reload_texture)',code)

if __name__=='__main__':unittest.main()
