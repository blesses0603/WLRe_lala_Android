"""Overlay state, permission plumbing and service isolation regressions."""
import json
import queue
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace

from android_app.overlay_state import snapshot
from android_app.runtime import Runtime


class OverlayStateTests(unittest.TestCase):
    def setUp(self):
        self.password = "super-private-password"
        self.manager = SimpleNamespace(lock=threading.RLock(), sessions={})
        self.manager.sessions["1"] = SimpleNamespace(
            lock=threading.RLock(), active=True, stop_event=threading.Event(),
            account="my-account", label="地球一線", phase="world_ready",
            automation={"battle": {"enabled": True, "status": "running"}})
        self.manager.sessions["2"] = SimpleNamespace(
            lock=threading.RLock(), active=False, stop_event=threading.Event(),
            account="another-account", label="水星二線", phase="disconnected",
            automation={"battle": {"enabled": True, "status": "running"}})

    def test_real_connection_and_battle_states_without_credentials(self):
        data = snapshot(self.manager)
        self.assertEqual((data["total"], data["active"], data["online"]), (2, 1, 1))
        self.assertEqual(data["accounts"][0]["battle"], "自動戰鬥中")
        self.assertEqual(data["accounts"][1]["battle"], "AI 未運作")
        self.assertIn("角色在線", data["accounts"][0]["connection"])
        output = json.dumps(data, ensure_ascii=False)
        self.assertNotIn("my-account", output)
        self.assertNotIn("another-account", output)
        self.assertNotIn(self.password, output)

    def test_battle_waiting_is_not_reported_as_fighting(self):
        session = self.manager.sessions["1"]
        session.automation["battle"]["status"] = "waiting_heal"
        self.assertEqual(snapshot(self.manager)["accounts"][0]["battle"], "AI 等待補給")
        session.automation["battle"]["status"] = "armed"
        self.assertEqual(snapshot(self.manager)["accounts"][0]["battle"], "AI 已啟用／待命")

    def test_no_account_and_many_accounts(self):
        self.manager.sessions.clear()
        self.assertEqual(snapshot(self.manager), {
            "total": 0, "active": 0, "online": 0, "accounts": []})
        for i in range(11):
            self.manager.sessions[str(i)] = SimpleNamespace(
                lock=threading.RLock(), active=True, stop_event=threading.Event(),
                account="private-" + str(i), label="server", phase="connecting",
                automation={})
        value = snapshot(self.manager)
        self.assertEqual(value["total"], 11)
        self.assertEqual(len(value["accounts"]), 6)

    def test_overlay_control_rejects_non_boolean_and_can_toggle(self):
        manager = SimpleNamespace(lock=threading.RLock(), sessions={},
            events=queue.Queue())
        manager.stop_all = lambda: None
        enabled = []
        runtime = Runtime(manager, lambda: {}, overlay_control=lambda value: enabled.append(value) or True,
                          overlay_state=lambda: enabled[-1] if enabled else False)
        self.assertFalse(runtime.dispatch({"op": "poll"})["overlay_enabled"])
        self.assertTrue(runtime.dispatch({"op": "overlay", "enabled": True}))
        self.assertTrue(runtime.dispatch({"op": "poll"})["overlay_enabled"])
        self.assertTrue(runtime.dispatch({"op": "overlay", "enabled": False}))
        self.assertFalse(runtime.dispatch({"op": "poll"})["overlay_enabled"])
        with self.assertRaises(ValueError):
            runtime.dispatch({"op": "overlay", "enabled": "yes"})

    def test_manifest_and_native_overlay_permission(self):
        root = Path(__file__).resolve().parents[1]
        spec = (root / "buildozer.spec").read_text(encoding="utf-8")
        native = (root / "android_app/java/org/lala/client/FloatingOverlay.java").read_text(encoding="utf-8")
        self.assertIn("SYSTEM_ALERT_WINDOW", spec)
        self.assertIn("TYPE_APPLICATION_OVERLAY", native)
        self.assertIn("Settings.canDrawOverlays", native)
        self.assertIn("FLAG_NOT_FOCUSABLE", native)
        self.assertIn("void destroy(", native)


if __name__ == "__main__":
    unittest.main()
