"""New Android IPC/data gates and touch commands use actual shared validators."""
import copy
import os
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from android_app.resource_sync import ResourceSync, configure_paths
from android_app.sessions import SessionManager
from android_app import features
from wlre.core.state import State


class AndroidResourceGate(unittest.TestCase):
    def test_launcher_receipt_and_version_match_cannot_authorize_login(self):
        for report in ({'status':'verified_official'}, {'login_allowed':True},
                       {'login_allowed':True,'database_verified':True,'blocked':True}):
            sync=ResourceSync(preparer=Mock(),checker=lambda:report)
            sync.start();sync.worker.join(2)
            self.assertFalse(sync.snapshot()['ready'])
            manager=SessionManager(resource_sync=sync)
            with self.assertRaises(ValueError):
                manager.start(label='test',host='example.invalid',port=1234,account='fixture',password='fixture')
            self.assertEqual(manager.sessions,{})

    def test_single_worker_and_verified_gate_only_after_database_check(self):
        entered,release=threading.Event(),threading.Event()
        def prepare(**kw):entered.set();release.wait(2)
        sync=ResourceSync(preparer=prepare,checker=lambda:dict(login_allowed=True,database_verified=True,blocked=False))
        self.assertTrue(sync.start());self.assertTrue(entered.wait(1))
        self.assertFalse(sync.start());self.assertFalse(sync.reset())
        release.set();sync.worker.join(2)
        sync.require_ready();self.assertTrue(sync.snapshot()['ready'])
        self.assertIn('catalog_token',sync.snapshot())

    def test_decoder_failure_is_sanitized_and_never_unlocks(self):
        sync=ResourceSync(preparer=Mock(side_effect=ValueError('PRIVATE-DEVICE-PATH-AND-SECRET')),checker=Mock())
        sync.start();sync.worker.join(2)
        self.assertFalse(sync.snapshot()['ready']);self.assertNotIn('PRIVATE',str(sync.snapshot()))
        sync.checker.assert_not_called()

    def test_android_private_directory_and_tls_roots_are_shared(self):
        context=Mock();context.getNoBackupFilesDir.return_value.getAbsolutePath.return_value='/private/fixture'
        with patch.dict(os.environ,{},clear=True):
            self.assertEqual(str(configure_paths(context)),'/private/fixture')
            self.assertEqual(os.environ['LOCALAPPDATA'],'/private/fixture')
            self.assertTrue(os.environ['SSL_CERT_FILE'].endswith('cacert.pem'))

    def test_state_projection_keeps_latest_features_but_no_credentials(self):
        state=State().snapshot();state['password']='synthetic'
        data=features.project(state)
        for name in ('npc_dialogue','shop_evidence','tent','time_cube','automation','room_storage','gold'):
            self.assertIn(name,data)
        self.assertNotIn('password',data)
        for name in ('npc_approach','npc_start','npc_next','npc_choose','tent','room_storage','time_cube','automatic_flows'):
            self.assertIn(name,features.GAME_COMMANDS)
        for name in ('npc_shop_buy','npc_shop_sell','instance_reward_paid','packet'):
            self.assertNotIn(name,features.GAME_COMMANDS)


class AndroidTransferAndCube(unittest.TestCase):
    def test_touch_transfer_uses_revisions_and_rejects_stale_item(self):
        from test_room_storage_transfer import ready
        from android_app.pages.storage import transfer_command
        state=ready().snapshot();item=copy.deepcopy(state['inventory']['items']['3'])
        selection=('materials','deposit',3,item,state['inventory']['revision'],state['room_storage']['revision'])
        command=transfer_command(state,selection,'2')
        self.assertEqual(command['count'],2)
        self.assertEqual(command['type'],'room_storage')
        state['inventory']['revision']+=1
        with self.assertRaises(ValueError):transfer_command(state,selection,'2')
        state['inventory']['items']['3']['serial']+=1
        with self.assertRaises(ValueError):transfer_command(state,selection,'2')

    def test_cube_page_emits_one_explicit_command_and_renders_pending(self):
        from android_app.pages.benefits import Benefits
        from test_time_cube import CubeTests
        fixture=CubeTests();fixture.setUp();state=fixture.state.snapshot()
        d=SimpleNamespace(state=state,live=True,send=Mock())
        page=Benefits(d);page.refresh()
        self.assertFalse(page.open_button.disabled)
        page.open_button.dispatch('on_release')
        d.send.assert_called_once_with(dict(type='time_cube',action='open'))
        state['time_cube']['pending']={'due':123};page.refresh()
        self.assertTrue(page.open_button.disabled)
        state['automation']['enabled']=False;page.refresh()
        self.assertIn('暫停',page.info.text)
