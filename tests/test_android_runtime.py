import json
import os
import queue
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from android_app.runtime import Runtime, LatestEvents, ServiceManager, receive, send
from android_app.vault import AccountVault


class FakeManager:
    def __init__(self):
        self.sessions = {}
        self.events = queue.Queue()
        self.lock = threading.RLock()
        self.stopped = []
    def stop_all(self): self.stopped.extend(self.sessions)
    def start(self, **args):
        if args.get('password') != 'secret': raise ValueError('secret credentials must not escape')
        sid = str(len(self.sessions))
        result = SimpleNamespace(session_id=sid, label=args['label'], account=args['account'],
            active=True, phase='role_selection', selection_pending=False,
            lock=threading.RLock(), stop_event=threading.Event())
        self.sessions[sid] = result
        self.events.put((sid, 'roles', [{'index': 1, 'locked': False}]))
        return result
    def select_role(self, sid, index):
        self.sessions[sid].selection_pending = True
        return True
    def stop(self, sid):
        self.sessions[sid].stop_event.set()
        self.stopped.append(sid)
        return True
    def remove(self, sid):
        self.sessions.pop(sid)
        return True


class RuntimeTests(unittest.TestCase):
    def test_snapshot_retained_for_new_activity_and_per_account_stop(self):
        manager = FakeManager()
        runtime = Runtime(manager, lambda: {'active': 2})
        for account in ('A', 'B'):
            runtime.dispatch({'op': 'start', 'args': dict(label='server', account=account, password='secret')})
        first = runtime.dispatch({'op': 'poll'})
        second = runtime.dispatch({'op': 'poll'})
        self.assertEqual(first, second)
        self.assertNotIn('secret', json.dumps(first))
        self.assertEqual(len(first['sessions']), 2)
        runtime.dispatch({'op': 'stop', 'id': '0'})
        self.assertEqual(manager.stopped, ['0'])
        self.assertFalse(manager.sessions['1'].stop_event.is_set())

    def test_monitor_failure_does_not_terminate_sessions_or_idle_server(self):
        def fail_telemetry():
            raise RuntimeError("DO_NOT_SHOW_ACCOUNT_PASSWORD")
        manager = FakeManager()
        runtime = Runtime(manager, fail_telemetry)
        session = manager.start(label="s", account="test", password="secret")
        first = runtime.dispatch({"op": "poll"})
        self.assertEqual(first["metrics"]["monitor_error"], "RuntimeError")
        self.assertEqual(len(first["sessions"]), 1)
        with tempfile.TemporaryDirectory() as folder:
            address = Path(folder) / "sock"
            worker = threading.Thread(target=runtime.serve, args=(address,))
            worker.start()
            try:
                deadline = time.monotonic() + 3
                while not address.exists() and time.monotonic() < deadline:
                    time.sleep(.02)
                time.sleep(1.2)  # Background heartbeat invokes faulty telemetry.
                self.assertTrue(worker.is_alive())
                with socket.socket(socket.AF_UNIX) as client:
                    client.connect(str(address))
                    with client.makefile("rwb") as stream:
                        send(stream, {"op": "poll"})
                        reply = receive(stream)
                self.assertTrue(reply["ok"])
                self.assertEqual(reply["value"]["metrics"]["monitor_error"], "RuntimeError")
                self.assertEqual(len(reply["value"]["sessions"]), 1)
                self.assertFalse(session.stop_event.is_set())
            finally:
                runtime.exit_requested = True
                worker.join(3)
                self.assertFalse(worker.is_alive())

    def test_failed_ipc_command_releases_pending_and_never_replays(self):
        manager = ServiceManager.__new__(ServiceManager)
        session = SimpleNamespace(selection_pending=True,
            automation_pending={"battle"})
        manager.sessions = {"s": session}
        manager.events = LatestEvents()
        requests = [
            ({"op": "select", "id": "s", "index": 1}, False),
            ({"op": "automation", "id": "s", "feature": "battle", "enabled": True}, True),
            ({"op": "game", "id": "s", "command": {
                "type": "chat", "request_id": "msg-1", "text": "private draft"}}, True),
            ({"op": "game", "id": "s", "command": {
                "type": "field_item", "item_id": 123}}, True),
        ]
        for request, uncertain in requests:
            manager._delivery_failed(request, uncertain=uncertain)
        self.assertFalse(session.selection_pending)
        self.assertNotIn("battle", session.automation_pending)
        events = []
        while True:
            try: events.append(manager.events.get_nowait())
            except queue.Empty: break
        ack = next(value for _, kind, value in events if kind == "chat_ack")
        self.assertEqual(ack, {"request_id": "msg-1", "status": "uncertain"})
        self.assertNotIn("private draft", str(events))
        self.assertTrue(any("結果無法確認" in value for _, kind, value in events
                            if kind == "error"))

    def test_private_socket_roundtrip_and_sanitized_error(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'ipc/sock'
            runtime = Runtime(FakeManager())
            thread = threading.Thread(target=runtime.serve, args=(path,))
            thread.start()
            try:
                for _ in range(100):
                    if path.exists(): break
                    time.sleep(.01)
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)
                def call(request):
                    with socket.socket(socket.AF_UNIX) as client:
                        client.connect(str(path))
                        with client.makefile('rwb') as stream:
                            send(stream, request)
                            return receive(stream)
                reply = call({'op': 'start', 'args': dict(password='wrong')})
                self.assertFalse(reply['ok'])
                self.assertNotIn('secret', json.dumps(reply))
                self.assertTrue(call({'op': 'poll'})['ok'])
                self.assertTrue(call({'op': 'shutdown'})['ok'])
            finally:
                runtime.exit_requested = True
                thread.join(3)
                self.assertFalse(thread.is_alive())

    def test_service_drains_events_without_an_activity(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = FakeManager()
            runtime = Runtime(manager)
            manager.start(label='s', account='a', password='secret')
            thread = threading.Thread(target=runtime.serve, args=(Path(directory) / 'sock',))
            thread.start()
            try:
                deadline = time.monotonic() + 3
                while not manager.events.empty() and time.monotonic() < deadline: time.sleep(.02)
                self.assertTrue(manager.events.empty())
                self.assertIn('roles', runtime.latest['0'])
            finally:
                runtime.exit_requested = True
                thread.join(3)

    def test_paused_ui_coalesces_updates_per_account(self):
        inbox = LatestEvents()
        for hp in range(10000):
            inbox.put(('A', 'snapshot', {'hp': hp}))
        inbox.put(('B', 'status', 'online'))
        inbox.put(('A', 'finished', 'stopped'))
        self.assertEqual(len(inbox.values), 3)
        self.assertEqual(inbox.get_nowait(), ('A', 'snapshot', {'hp': 9999}))
        self.assertEqual(inbox.get_nowait(), ('B', 'status', 'online'))
        self.assertEqual(inbox.get_nowait(), ('A', 'finished', 'stopped'))
        with self.assertRaises(queue.Empty): inbox.get_nowait()

    def test_rejected_select_replays_unchanged_roles(self):
        # Simulate a server rejecting selection with the same role list.
        # End-to-end event retention itself must preserve roles after rejection.
        manager = FakeManager(); runtime = Runtime(manager)
        manager.start(label='s', account='a', password='secret')
        runtime.dispatch({'op': 'poll'})
        manager.events.put(('0', 'status', '角色選擇未成功'))
        data = runtime.dispatch({'op': 'poll'})
        self.assertIn('roles', data['sessions'][0]['events'])
        self.assertIn('未成功', data['sessions'][0]['events']['status'])


class VaultTests(unittest.TestCase):
    def test_ciphertext_roundtrip_delete_and_tampering(self):
        # Desktop AESGCM exercises persistence without pretending to test Keystore.
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        except ImportError: self.skipTest('cryptography test dependency unavailable')
        import base64
        class Cipher:
            key = AESGCM.generate_key(bit_length=256)
            def encrypt(self, data):
                iv = os.urandom(12)
                return dict(iv=base64.b64encode(iv).decode(),
                    data=base64.b64encode(AESGCM(self.key).encrypt(iv, data, None)).decode())
            def decrypt(self, value):
                return AESGCM(self.key).decrypt(base64.b64decode(value['iv']),
                    base64.b64decode(value['data']), None)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'accounts.enc'
            cipher = Cipher(); vault = AccountVault(path, cipher)
            records = [dict(account='fixture-user', password='fixture-secret', server='s')]
            self.assertEqual(vault.load(), [])
            vault.save(records)
            self.assertNotIn('fixture-secret', path.read_text())
            self.assertNotIn('fixture-user', path.read_text())
            self.assertEqual(AccountVault(path, cipher).load(), records)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            vault.save([])
            self.assertEqual(vault.load(), [])
            value = json.loads(path.read_text()); value['data'] = base64.b64encode(b'bad').decode()
            path.write_text(json.dumps(value))
            with self.assertRaises(Exception): vault.load()
            self.assertEqual(json.loads(path.read_text()), value)
