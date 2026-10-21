"""Android parity checkpoint: source-verified catalog and no unsafe commands."""
import unittest

from android_app.features import GAME_COMMANDS, checked_command
from android_app.pages.attributes import attribute_lines
from wlre.services.instance_browser import official_catalog, entries_for
from android_app.pages.instances import describe_entry


class AndroidReadOnlyParity(unittest.TestCase):
    def test_official_1262_catalog_is_complete_and_read_only(self):
        data = official_catalog()
        self.assertEqual(data["version"], 1262)
        self.assertEqual(data["counts"]["dungeon_records"], 30)
        self.assertEqual(len(entries_for("main")), 27)
        self.assertEqual(len(entries_for("coop")), 3)
        self.assertTrue(all(row.get("name") for row in data["records"]))
        self.assertIn("靜態資料", describe_entry(entries_for("main")[0]))
        with self.assertRaises(ValueError):
            entries_for("unknown")

    def test_no_room_or_allocation_operations_cross_ipc(self):
        self.assertNotIn("instance_create", GAME_COMMANDS)
        self.assertNotIn("instance_join", GAME_COMMANDS)
        self.assertNotIn("instance_claim", GAME_COMMANDS)
        self.assertNotIn("allocate_attributes", GAME_COMMANDS)
        for name in ("instance_create", "instance_join", "instance_claim", "allocate_attributes"):
            with self.assertRaises(ValueError):
                checked_command({"type": name})

    def test_attributes_do_not_invent_missing_or_unconfirmed_values(self):
        self.assertIn("尚未", "\n".join(attribute_lines({})))
        state = {"knowledge": {"player": {"ready": True, "stats": {
            "int": 12, "str": 9, "con": 6, "agi": 5, "wis": 7,
            "attribute_potential": 0}}}}
        text = "\n".join(attribute_lines(state))
        self.assertIn("智力 INT：12", text)
        self.assertIn("剩餘可配點：0", text)
        state["knowledge"]["player"]["stats"].pop("int")
        self.assertIn("智力 INT：待同步", "\n".join(attribute_lines(state)))


if __name__ == "__main__":
    unittest.main()
