"""Regression contracts for Android reference-fidelity verification gateway."""
import ast
import importlib.util
import os
from pathlib import Path
import unittest

from android_app.verification_presenter import CHECKS, verification_view_state

ROOT = Path(__file__).resolve().parents[1]
ASSET = ROOT / 'android_app/assets/verification_castle.jpg'


def resource(status='checking', ready=False, **kwargs):
    return dict(status=status, ready=ready, **kwargs)


def verified_state():
    token = [True, 'a' * 64]
    return (resource('ready', True, catalog_token=token),
            resource('ready', True, catalog_token=token))


class VerificationPresenterTests(unittest.TestCase):
    def test_exact_seven_rows_in_reference_order(self):
        self.assertEqual([name for _, name, _ in CHECKS],
                         ['官方版本', 'DataPackage', 'MainPackage',
                          'Manifest', 'Bundle', 'Runtime', 'SQLite'])

    def test_waiting_offline_is_not_a_green_success(self):
        state = verification_view_state({}, {}, connected=False)
        self.assertEqual(state['overall'], 'waiting')
        self.assertFalse(state['complete'])
        self.assertEqual(state['steps'], ('waiting',) * 7)
        self.assertEqual(state['checked_at'], '尚無紀錄')
        self.assertEqual(state['versions'], {})

    def test_a_version_number_cannot_unlock_login_or_fake_success(self):
        state = verification_view_state(resource(
            'checking', package_versions={
                'DataPackage': '1286',
                'MainPackage': '1284',
                'other': 'secret',
            }), {}, connected=True)
        self.assertEqual(state['versions'], {
            'DataPackage': '1286', 'MainPackage': '1284',
        })
        self.assertNotIn('success', state['steps'])
        self.assertEqual(state['overall'], 'checking')
        self.assertFalse(state['complete'])

    def test_identity_and_bundle_milestones_are_not_sqlite_success(self):
        state = verification_view_state(resource(
            'checking', progress_phase='runtime_identity_verified'), {},
            connected=True)
        self.assertEqual(state['steps'][:4], ('success',) * 4)
        self.assertEqual(state['steps'][4:], ('waiting',) * 3)
        state = verification_view_state(resource(
            'checking', progress_phase='runtime_bundle_ready'), {},
            connected=True)
        self.assertEqual(state['steps'][4], 'success')
        self.assertEqual(state['steps'][5], 'checking')
        self.assertEqual(state['steps'][6], 'waiting')

    def test_service_ready_still_waits_for_activity_sqlite_identity(self):
        service, local = verified_state()
        local['status'] = 'checking'
        local['ready'] = False
        state = verification_view_state(service, local, connected=True)
        self.assertEqual(state['steps'][:6], ('success',) * 6)
        self.assertEqual(state['steps'][6], 'checking')
        self.assertNotEqual(state['overall'], 'success')

    def test_local_failure_reports_failure_not_fake_success(self):
        service, local = verified_state()
        local.update(status='blocked', ready=False, message='本機比對失敗')
        state = verification_view_state(service, local, connected=True)
        self.assertEqual(state['overall'], 'error')
        self.assertEqual(state['steps'][-1], 'error')
        self.assertFalse(state['complete'])
        self.assertIn('本機比對失敗', state['detail'])

    def test_both_valid_tokens_are_required_for_all_success(self):
        service, local = verified_state()
        state = verification_view_state(service, local, connected=True)
        self.assertTrue(state['complete'])
        self.assertEqual(state['steps'], ('success',) * 7)
        self.assertEqual(state['headline'], '所有項目驗證通過')
        local['catalog_token'] = [True, 'b' * 64]
        state = verification_view_state(service, local, connected=True)
        self.assertFalse(state['complete'])
        self.assertNotEqual(state['overall'], 'success')

    def test_no_stale_or_untrusted_version_timestamp(self):
        state = verification_view_state(resource(
            'blocked', package_versions={'DataPackage': 'PRIVATE',
            'MainPackage': '1284_EXTRA_TEXT'}, checked_at='SECRET',
            message='檢查未通過'), {}, connected=True)
        self.assertEqual(state['versions'], {})
        self.assertEqual(state['checked_at'], '尚無紀錄')
        self.assertEqual(state['overall'], 'error')

    def test_new_ui_code_is_parseable_and_uses_real_widgets(self):
        for name in ('android_app/verification_ui.py',
                     'android_app/verification_presenter.py',
                     'android_app/app.py', 'android_app/resource_sync.py'):
            ast.parse((ROOT / name).read_text('utf-8'), filename=name)
        code = (ROOT / 'android_app/verification_ui.py').read_text('utf-8')
        self.assertIn('class VerificationHero(FloatLayout)', code)
        self.assertIn('class VerificationStep(BoxLayout)', code)
        self.assertIn("verification_castle.jpg", code)
        self.assertIn('for index, (_, name, detail) in enumerate(CHECKS, 1):', code)
        self.assertNotIn('所有項目驗證通過', code)
        self.assertNotIn('2025-01-26', code)

    def test_reference_art_is_bundled_not_downloaded(self):
        from PIL import Image as PILImage
        with PILImage.open(ASSET) as artwork:
            artwork.verify()
        spec = (ROOT / 'buildozer.spec').read_text('utf-8')
        self.assertIn('jpg', spec.split('source.include_exts = ', 1)[1].splitlines()[0])
        self.assertLess(ASSET.stat().st_size, 10 * 1024)


HAS_KIVY = importlib.util.find_spec('kivy') is not None


@unittest.skipUnless(HAS_KIVY and (os.environ.get('DISPLAY') or os.name == 'nt'),
                     'Requires Kivy with a display')
class VerificationWidgetTests(unittest.TestCase):
    def test_seven_real_rows_and_live_version_cards(self):
        from kivy.clock import Clock
        from kivy.uix.scrollview import ScrollView
        from android_app.verification_ui import VerificationScreen
        actions = []
        panel = VerificationScreen(
            lambda: actions.append('retry'),
            lambda: actions.append('restart'))
        self.assertIsInstance(panel, ScrollView)
        self.assertEqual(len(panel.steps), 7)
        self.assertTrue(all(row.current == 'waiting' for row in panel.steps))
        panel.size = (320, 640)
        for _ in range(4):
            Clock.tick()
        model = verification_view_state(
            resource('checking', package_versions={
                'DataPackage': '1286', 'MainPackage': '1284',
            }), {}, connected=True)
        panel.render(model)
        self.assertEqual(panel.version_values['DataPackage'].text, '1286')
        self.assertEqual(panel.version_values['MainPackage'].text, '1284')
        self.assertIn('驗證中', panel.header.status.text)
        panel.retry.dispatch('on_release')
        panel.restart.dispatch('on_release')
        self.assertEqual(actions, ['retry', 'restart'])

    def test_only_real_dual_token_verification_paints_seven_green_rows(self):
        from android_app.verification_ui import VerificationScreen
        panel = VerificationScreen(lambda: None, lambda: None)
        service, local = verified_state()
        panel.render(verification_view_state(service, local, connected=True))
        self.assertTrue(all(row.current == 'success' for row in panel.steps))
        self.assertIn('完成', panel.header.status.text)
        panel.render(verification_view_state({}, {}, connected=False))
        self.assertTrue(all(row.current == 'waiting' for row in panel.steps))
        self.assertNotIn('完成', panel.header.status.text)


if __name__ == '__main__':
    unittest.main()
