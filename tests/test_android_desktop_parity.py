"""Android-specific integration checks for WLRe_lala main's shared features."""
import copy
import unittest

from android_app import features, preferences
from android_app.bag_model import PAGE_SIZE, COLUMNS, visible_items, item_details
from android_app.sessions import Session, SessionManager
from wlre.core.state import State
from wlre.services.expedition_data import load_catalog
from wlre.services.expedition import validate as validate_expedition
from wlre.services.items.room_storage import defaults as storage_defaults
from wlre.services.battle.auto_battle import defaults as ai_defaults


class LatestDesktopCoreOnAndroid(unittest.TestCase):
    def test_official_expedition_catalog_and_settings_are_bundled(self):
        data = load_catalog()
        self.assertEqual(len(data["tasks"]), 260)
        self.assertEqual(len(data["levels"]), 10)
        self.assertTrue(data["npcs"])
        checked = validate_expedition(preferences.defaults()["expedition"])
        self.assertEqual(checked["min_success"], 75)
        self.assertEqual(checked["faith_min"], 80)
        self.assertEqual(checked["min_hours"], 0)
        self.assertTrue(checked["auto_claim"])

    def test_new_state_and_operations_cross_mobile_feature_gate(self):
        state = State().snapshot()
        for field in ("expedition", "maintenance", "room_storage"):
            self.assertIn(field, features.project(state))
        self.assertFalse(state["expedition"]["enabled"])
        self.assertFalse(state["room_storage"]["garage"]["ready"])
        for action in (
            {"type": "companion", "action": "deploy", "index": 1, "npc_id": 100},
            {"type": "start_expedition", "settings": validate_expedition({})},
            {"type": "stop_expedition"},
        ):
            self.assertEqual(features.checked_command(action), action)

    def test_saved_expedition_does_not_auto_launch_any_action(self):
        manager = SessionManager()
        session = Session("sid", "地球", "fixture", "server.invalid", 1234)
        session.phase = "world_ready"
        session.preferences = preferences.defaults()
        manager.sessions[session.session_id] = session
        self.assertFalse(session.commands.qsize())
        changed = preferences.validate({
            "favorites": [], "plan": [],
            "expedition": {**session.preferences["expedition"], "min_success": 88},
        })
        self.assertTrue(manager.save_preferences("sid", changed))
        self.assertEqual(session.preferences["expedition"]["min_success"], 88)
        self.assertTrue(session.commands.empty())
        self.assertTrue(manager.automation_command("sid", "expedition", True))
        command = session.commands.get_nowait()
        self.assertEqual(command["type"], "start_expedition")
        self.assertEqual(command["settings"]["min_success"], 88)
        self.assertIn("expedition", session.automation_pending)
        session.automation_pending.clear()
        self.assertTrue(manager.automation_command("sid", "expedition", False))
        self.assertEqual(session.commands.get_nowait(), {"type": "stop_expedition"})

    def test_ai_maintenance_preferences_are_validated_by_core(self):
        original = ai_defaults()
        self.assertIn("maintenance", original)
        self.assertEqual(len(original["maintenance"]["repair_items"]), 2)
        self.assertEqual(len(original["maintenance"]["cleanup_items"]), 15)
        from wlre.services.battle.auto_battle import validate
        self.assertEqual(validate(original)["maintenance"], original["maintenance"])

    def test_inventory_stays_authoritative_and_read_only_storage_is_separate(self):
        inv = {"ready": True, "reliable": True, "reserved": {"8": 2},
               "items": {"8": {"index": 8, "item_id": 34144, "count": 6},
                         "2": {"index": 2, "item_id": 34026, "count": 5}}}
        self.assertEqual(PAGE_SIZE, 24)
        self.assertEqual(COLUMNS, 4)  # Narrow portrait layout, unlike desktop 6x4.
        self.assertEqual([key for key, _, _ in visible_items(inv)], ["2", "8"])
        item = item_details(inv, "8", inv["items"]["8"])
        self.assertEqual(item["available"], 4)
        self.assertEqual(item["count"], 6)
        remote = storage_defaults()
        self.assertFalse(remote["garage"]["ready"])
        self.assertFalse(remote["materials"]["ready"])
        self.assertNotIn("8", remote["garage"]["items"])
        self.assertNotIn("8", remote["materials"]["items"])


if __name__ == "__main__":
    unittest.main()
