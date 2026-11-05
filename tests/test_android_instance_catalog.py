"""Android parity: only explicit, validated instance commands cross IPC."""
import unittest

from android_app.features import GAME_COMMANDS, checked_command
from android_app.pages.attributes import attribute_lines
from wlre.services.instance_browser import entries_for
from wlre.services import instance_browser
from android_app.pages.instances import describe_entry


class AndroidReadOnlyParity(unittest.TestCase):
    def test_official_1262_catalog_is_complete_and_read_only(self):
        data = instance_browser.official_catalog()
        self.assertEqual(data["source"], "synthetic_test")
        self.assertEqual(data["counts"]["dungeon_records"], 8)
        self.assertEqual(len(entries_for("main")), 5)
        self.assertEqual(len(entries_for("coop")), 3)
        self.assertTrue(all(row.get("name") for row in data["records"]))
        self.assertIn("靜態資料", describe_entry(entries_for("main")[0]))
        with self.assertRaises(ValueError):
            entries_for("unknown")

    def test_cold_start_has_no_creation_choices(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from wlre.network.wire import ProtocolError
        from android_app.pages.instances import InstanceCatalog
        page=SimpleNamespace(rows=lambda:entries_for('main'), info=SimpleNamespace(text=''),
                             details=SimpleNamespace(text=''),current_mode=lambda:'main',
                             d=SimpleNamespace(live=True,message=SimpleNamespace(text='')))
        with patch('wlre.services.instance_browser.official_catalog',side_effect=ProtocolError('未同步')), patch(
                'android_app.pages.instances.pick') as choose:
            InstanceCatalog.render(page)
            self.assertIn('等待官方',page.info.text)
            InstanceCatalog.create_room(page)
            choose.assert_not_called()
            self.assertIn('可用的官方',page.d.message.text)

    def test_explicit_room_operations_and_allocation_allowlist(self):
        for name in ("instance_create", "instance_join", "instance_leave",
                     "instance_coop_standby", "instance_start", "instance_enter",
                     "instance_auto_reward", "instance_reward_claim",
                     "instance_reward_cancel", "allocate_points"):
            self.assertIn(name, GAME_COMMANDS)
            self.assertEqual(checked_command({"type": name}), {"type": name})
        # Never accidentally allow unknown, paid or NPC actions.
        for name in ("instance_claim", "allocate_attributes",
                     "npc_shop", "npc_shop_buy", "npc_shop_sell", "instance_paid_reward"):
            self.assertNotIn(name, GAME_COMMANDS)
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



from instance_runtime_fixtures import install as setUpModule
