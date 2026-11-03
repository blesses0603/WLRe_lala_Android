"""Android-only UI refresh performance guards; no Kivy display required."""
from pathlib import Path
from types import SimpleNamespace
import threading
import unittest

from android_app.refresh_policy import RefreshPolicy
from android_app.runtime import LatestEvents, ServiceManager

ROOT = Path(__file__).resolve().parents[1]


class DashboardRefreshPolicyTests(unittest.TestCase):
    def test_static_page_skips_identical_snapshots_for_five_seconds(self):
        gate = RefreshPolicy()
        self.assertTrue(gate.should_refresh('包包與特技', 1, True, 0))
        for at in (0.5, 1, 2, 3, 4, 4.99):
            self.assertFalse(gate.should_refresh('包包與特技', 1, True, at))
        self.assertTrue(gate.should_refresh('包包與特技', 1, True, 5))

    def test_burst_updates_are_coalesced_but_latest_revision_is_not_lost(self):
        gate = RefreshPolicy()
        self.assertTrue(gate.should_refresh('煉金', 1, True, 10))
        self.assertFalse(gate.should_refresh('煉金', 2, True, 10.5))
        self.assertFalse(gate.should_refresh('煉金', 3, True, 10.7))
        self.assertTrue(gate.should_refresh('煉金', 3, True, 11))
        self.assertFalse(gate.should_refresh('煉金', 3, True, 11.5))

    def test_navigation_and_connection_changes_bypass_throttle(self):
        gate = RefreshPolicy()
        self.assertTrue(gate.should_refresh('包包與特技', 1, True, 0))
        self.assertTrue(gate.should_refresh('小地圖', 1, True, 0.1))
        self.assertTrue(gate.should_refresh('小地圖', 1, False, 0.2))
        self.assertTrue(gate.should_refresh('小地圖', 1, True, 0.3))

    def test_periodic_pages_keep_countdown_and_chat_timeouts(self):
        for page, interval in (('遠征', 1), ('製作', 1),
                               ('副本資料', 1), ('經驗效率', 1),
                               ('聊天', 0.5)):
            with self.subTest(page=page):
                gate = RefreshPolicy()
                self.assertTrue(gate.should_refresh(page, 1, True, 0))
                self.assertFalse(gate.should_refresh(page, 1, True,
                                                     interval - 0.01))
                self.assertTrue(gate.should_refresh(page, 1, True, interval))

    def test_no_refresh_without_visible_page(self):
        self.assertFalse(RefreshPolicy().should_refresh(None, 1, True, 1))

    def test_lazy_page_imports_do_not_preload_unvisited_pages(self):
        # The dashboard module itself is Kivy-dependent; source assertions
        # make this regression runnable in minimal no-GUI GitHub CI.
        content = (ROOT / 'android_app/dashboard.py').read_text('utf-8')
        show = content.split('    def show(self, name):', 1)[1].split(
            '    def tick(self, *_):', 1)[0]
        self.assertIn("import_module('android_app.pages.' + module)", show)
        self.assertNotIn('from android_app.pages.resources import Resources', show)
        self.assertEqual(content.count("'包包與特技': ('resources', 'Resources')"), 1)
        self.assertIn('if name not in self.views:', show)


class ServiceSnapshotRevisionTests(unittest.TestCase):
    def test_equal_detail_is_not_republished_and_changed_detail_is_not_lost(self):
        service = ServiceManager.__new__(ServiceManager)
        service.sessions = {}
        service.events = LatestEvents()
        service.metrics = {}
        service.resource_status = {}
        service.overlay_enabled = False
        service.available = False
        service._last = {}
        service.details = {}
        service.detail_revisions = {}
        service.watched = 'A'
        service._resource_request_pending = False
        state = {'state': {'hp': 20}, 'chat': []}
        snapshot = {
            'sessions': [dict(id='A', label='server', account='demo',
                              active=True, phase='world_ready', pending=False,
                              stopped=False, events={})],
            'metrics': {'active': 1},
            'resources': {'status': 'ready'},
        }

        def call(request):
            if request['op'] == 'poll':
                return snapshot
            self.assertEqual(request, {'op': 'detail', 'id': 'A'})
            return {'state': dict(state['state']), 'chat': list(state['chat'])}

        service.call = call
        service._poll_once()
        self.assertEqual(service.detail_revisions['A'], 1)
        original = service.details['A']
        service._poll_once()
        self.assertEqual(service.detail_revisions['A'], 1)
        self.assertIs(service.details['A'], original)
        state['state']['hp'] = 12
        service._poll_once()
        self.assertEqual(service.detail_revisions['A'], 2)
        self.assertEqual(service.session_detail('A')['state']['hp'], 12)

        service.watch(None)
        self.assertEqual(service.details, {})
        self.assertEqual(service.detail_revisions, {})
        service._poll_once()
        self.assertEqual(service.detail_revisions, {})


if __name__ == '__main__':
    unittest.main()
