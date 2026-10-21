"""Overlay state, permission plumbing and service isolation regressions."""
import json
import queue
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace

from android_app.overlay_state import snapshot
from android_app.overview_model import overview_model, overview_lines
from android_app.runtime import Runtime
from wlre.core.state import State
from wlre.network.protocol import decode
from wlre.network.wire import Packet


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

    def test_character_overview_reuses_live_battle_stats_and_labels(self):
        first = self.manager.sessions["1"]
        first.game_state = {
            "player": {"name": "赤寧", "role_id": 11},
            "knowledge": {
                "player": {"stats": {"level": 172, "hp": 1400, "max_hp": 2000, "sp": 250, "max_sp": 500}},
                "companions": {"1": {"npc_id": 999999, "stats": {
                    "level": 128, "hp": 500, "max_hp": 1000, "sp": 80, "max_sp": 200}}},
                "active_npc_id": 999999},
            "battle": {"active": True},
            "battle_units": {"1": {"pid": 11, "hp": 1000, "sp": 180}},
            "auto_battle": {"status": "armed", "reason": "玩家已登入"},
            "roaming": {"status": "disabled"},
            "event_flow": {"blocked": True},
            "alchemy": {"status": "煉金中"},
            "crafting": {"status": "製作中"},
            "inventory": {"field_supply": {"reason": "待補給"}},
        }
        full = overview_model(first.game_state)
        rows = overview_lines(first.game_state)
        self.assertEqual(full["character"], "赤寧")
        self.assertIn("角色 Lv.172\nHP 1000/2000 · SP 180/500", rows)
        self.assertIn("夥伴（出戰） Lv.128\nHP 500/1000 · SP 80/200", rows)
        self.assertIn("自動戰鬥：AI待命｜玩家已登入", rows)
        self.assertIn("事件：等待伺服器事件結束", rows)
        projected = snapshot(self.manager)
        overview = projected["accounts"][0]["overview"]
        self.assertEqual(overview["character"], "赤寧")
        self.assertEqual(projected["accounts"][0]["name"], "赤寧")
        self.assertEqual(overview["profiles"][0]["hp"], "1000")
        self.assertEqual(overview["profiles"][0]["sp"], "180")
        self.assertEqual(overview["statuses"]["battle"], full["statuses"]["battle"])
        self.assertEqual(set(overview["statuses"]), {"battle", "roaming", "event"})
        self.assertNotIn("alchemy", overview["statuses"])
        self.assertNotIn("crafting", overview["statuses"])
        self.assertNotIn("supply", overview["statuses"])
        self.assertEqual(overview["statuses"]["event"], full["statuses"]["event"])
        serialized = json.dumps(projected, ensure_ascii=False)
        self.assertNotIn("my-account", serialized)
        self.assertNotIn("another-account", serialized)
        self.assertNotIn(self.password, serialized)

    def test_disconnected_account_does_not_leak_old_character(self):
        first = self.manager.sessions["1"]
        first.game_state = {"player": {"name": "過期角色"}}
        first.active = False
        result = snapshot(self.manager)
        self.assertIsNone(result["accounts"][0]["overview"])
        self.assertEqual(result["accounts"][0]["name"], "角色 1（等待登入）")
        self.assertNotIn("過期角色", json.dumps(result, ensure_ascii=False))

    def test_overview_is_bounded_and_sanitized(self):
        first = self.manager.sessions["1"]
        first.game_state = {
            "player": {"name": "星" * 100 + "\n不應顯示"},
            "knowledge": {"companions": {
                str(i): {"npc_id": i, "stats": {"level": i}} for i in range(24)}},
            "alchemy": {"status": "煉" * 200},
        }
        result = snapshot(self.manager)["accounts"][0]["overview"]
        self.assertEqual(len(result["profiles"]), 1)  # No S19-confirmed active companion.
        self.assertEqual(result["profiles"][0]["name"], "角色")
        self.assertEqual(result["remaining_profiles"], 0)
        self.assertEqual(len(result["character"]), 32)
        self.assertEqual(set(result["statuses"]), {"battle", "roaming", "event"})
        self.assertNotIn("\n", result["character"])

    def test_only_authoritatively_deployed_companion_appears(self):
        first = self.manager.sessions["1"]
        first.game_state = {
            "player": {"name": "角色甲", "role_id": 12},
            "knowledge": {
                "player": {"stats": {"level": 99}},
                "companions_ready": True,
                "companions": {
                    "1": {"npc_id": 101, "name": "待命甲",
                          "stats": {"level": 11}},
                    "2": {"npc_id": 202, "name": "出戰乙",
                          "stats": {"level": 22, "hp": 30, "max_hp": 50}},
                    "3": {"npc_id": 303, "name": "待命丙",
                          "stats": {"level": 33}},
                },
                "active_npc_id": 202,
            },
        }
        overview = snapshot(self.manager)["accounts"][0]["overview"]
        self.assertEqual([p["name"] for p in overview["profiles"]],
                         ["角色", "出戰乙（出戰）"])
        self.assertEqual(overview["profiles"][1]["level"], "22")
        self.assertEqual(overview["remaining_profiles"], 0)
        lines = overview_lines(first.game_state)
        self.assertTrue(any(v.startswith("出戰乙（出戰） Lv.22\n") for v in lines))
        self.assertFalse(any("待命甲" in v or "待命丙" in v for v in lines))
        serialized = json.dumps(overview, ensure_ascii=False)
        self.assertNotIn("待命甲", serialized)
        self.assertNotIn("待命丙", serialized)

    def test_s19_deploy_switch_rest_auto_updates_overview(self):
        state = State(phase="world_ready")
        state.player = {"role_id": 12, "name": "角色甲"}
        state.knowledge.update(
            companions_ready=True,
            companions={
                "1": {"npc_id": 101, "stats": {"level": 11}},
                "2": {"npc_id": 202, "stats": {"level": 22}},
            },
        )
        first = self.manager.sessions["1"]
        first.game_state = state.snapshot()

        def names():
            return [p["name"] for p in snapshot(self.manager)["accounts"][0]["overview"]["profiles"]]

        self.assertEqual(names(), ["角色"])  # No confirmed deployed companion.
        state.apply(decode(Packet(19, 1, (101).to_bytes(4, "little"))))
        first.game_state = state.snapshot()
        self.assertEqual(len(names()), 2)
        self.assertTrue(names()[1].endswith("（出戰）"))

        state.apply(decode(Packet(19, 4, (202).to_bytes(4, "little"))))
        first.game_state = state.snapshot()
        self.assertEqual(len(names()), 2)
        self.assertEqual(overview_model(first.game_state)["profiles"][1]["level"], 22)

        state.apply(decode(Packet(19, 2, b"")))
        first.game_state = state.snapshot()
        self.assertEqual(names(), ["角色"])  # Rest removes the partner row.

    def test_missing_or_invalid_active_companion_never_guesses(self):
        state = {
            "knowledge": {
                "player": {"stats": {"level": 8}},
                "companions": {
                    "1": {"npc_id": 101, "stats": {"level": 11}},
                    "2": {"npc_id": 202, "stats": {"level": 22}},
                },
            },
        }
        for active in (None, 0, False, -1, 999, "101"):
            with self.subTest(active=active):
                state["knowledge"]["active_npc_id"] = active
                self.assertEqual(len(overview_model(state)["profiles"]), 1)
        # Even when the server roster contains duplicate IDs, do not repeat
        # a deployed partner in the small overlay.
        state["knowledge"]["companions"]["2"]["npc_id"] = 101
        state["knowledge"]["active_npc_id"] = 101
        self.assertEqual(len(overview_model(state)["profiles"]), 2)

    def test_overlay_companions_are_isolated_between_accounts(self):
        first = self.manager.sessions["1"]
        second = self.manager.sessions["2"]
        second.active, second.phase = True, "world_ready"
        for session, active in ((first, 101), (second, None)):
            session.game_state = {
                "player": {"name": "甲" if session is first else "乙"},
                "knowledge": {
                    "player": {"stats": {}},
                    "companions": {"1": {"npc_id": 101, "stats": {}}},
                    "active_npc_id": active,
                },
            }
        rows = snapshot(self.manager)["accounts"]
        self.assertEqual(len(rows[0]["overview"]["profiles"]), 2)
        self.assertEqual(len(rows[1]["overview"]["profiles"]), 1)

    def test_native_bubble_uses_same_app_icon_and_role_overview(self):
        root = Path(__file__).resolve().parents[1]
        java = (root / "android_app/java/org/lala/client/FloatingOverlay.java").read_text("utf-8")
        page = (root / "android_app/pages/general.py").read_text("utf-8")
        self.assertIn("getApplicationIcon(context.getPackageName())", java)
        self.assertIn('overview.optJSONArray("profiles")', java)
        self.assertIn("addVital(context, card", java)
        self.assertIn('addStatus(context, card, "事件"', java)
        self.assertIn('overview.optJSONArray("efficiency")', java)
        self.assertNotIn('TextView character = text(context,', java)
        for hidden in ("煉金", "製作", "補給"):
            self.assertNotIn('addStatus(context, card, "' + hidden + '"', java)
        self.assertIn("overview_lines(self.state)", page)

    def test_overlay_exp_efficiency_uses_confirmed_samples_only(self):
        first = self.manager.sessions["1"]
        first.game_state = {
            "player": {"name": "星崆"},
            "efficiency": {"rows": {"self": {
                "name": "星崆", "count": 2, "earned": 600,
                "first_time": 100., "last_time": 700.,
                "history": [(0, 100.), (600, 700.)],
            }}},
        }
        data = snapshot(self.manager)
        self.assertEqual(data["accounts"][0]["name"], "星崆")
        values = data["accounts"][0]["overview"]["efficiency"]
        self.assertEqual(values[0]["name"], "角色")
        self.assertEqual(values[0]["average"], "3,600 EXP/時")
        self.assertEqual(values[0]["recent10"], "3,600 EXP/時")
        self.assertNotIn("my-account", json.dumps(data, ensure_ascii=False))

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
