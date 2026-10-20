"""Desktop v0.5.6 post-battle coordination and inventory hold regressions.

Use authoritative state updates; do not fabricate successful packet outcomes.
"""
import unittest
from unittest.mock import patch

from wlre.core.state import State
from wlre.core.state_events import WORLD_KINDS, BATTLE_KINDS, SESSION_KINDS
from wlre.network.client import SessionLogic
from wlre.network.wire import ProtocolError
from wlre.services.coordination import command_reason, reason
from wlre.services.items import reservations
from wlre.services.items.combat_resources import available
from wlre.services.items.field_supply import FieldSupply


def inventory():
    return {
        "ready": True, "reliable": True, "revision": 1,
        "items": {
            "1": {"item_id": 100, "serial": 20, "serial_version": 1, "count": 3},
            "2": {"item_id": 200, "serial": 30, "serial_version": 1, "count": 2},
        },
        "reserved": {},
    }


class SharedBagHolds(unittest.TestCase):
    def test_atomic_acquire_does_not_hold_partial_batch(self):
        inv = inventory()
        with self.assertRaises(ProtocolError):
            reservations.acquire(inv, "maintenance", [
                {"index": 1, "count": 1, "item_id": 100},
                {"index": 2, "count": 3, "item_id": 200},
            ], exclusive=True)
        self.assertEqual(inv["reserved"], {})
        self.assertFalse(inv.get("holds", {}))

    def test_other_consumer_cannot_use_unconfirmed_maintenance_slot(self):
        inv = inventory()
        reservations.acquire(inv, "maintenance",
                             [{"index": 1, "item_id": 100, "count": 1}],
                             exclusive=True)
        self.assertEqual(available(inv, 1), 0)
        self.assertEqual(inv["maintenance_slots"], ["1"])
        with self.assertRaises(ProtocolError):
            reservations.acquire(inv, "field_supply",
                                 [{"index": 1, "item_id": 100, "count": 1}])
        self.assertFalse(inv.get("holds", {}).get("field_supply"))

    def test_snapshot_does_not_unlock_pending_item(self):
        inv = inventory()
        reservations.acquire(inv, "field_supply",
                             [{"index": 1, "count": 1, "item_id": 100}],
                             exclusive=True)
        fresh = inventory()
        fresh["items"]["1"]["count"] = 2
        reservations.refreshed(inv, fresh)
        self.assertEqual(fresh["reserved"]["1"], 0)
        self.assertEqual(available(fresh, 1), 0)  # exclusive until HP/SP confirmation
        reservations.release(fresh, "field_supply")
        self.assertEqual(available(fresh, 1), 2)

    def test_uncertain_hold_survives_identity_replacement(self):
        inv = inventory()
        reservations.acquire(inv, "maintenance",
                             [{"index": 1, "count": 1, "item_id": 100}], exclusive=True)
        reservations.uncertain(inv, "maintenance")
        fresh = inventory()
        fresh["items"]["1"]["serial"] = 999
        reservations.refreshed(inv, fresh)
        self.assertFalse(fresh["reliable"])
        self.assertEqual(available(fresh, 1), 0)
        self.assertTrue(fresh["holds"]["maintenance"][0]["uncertain"])

    def test_legacy_reservations_are_still_respected(self):
        inv = inventory()
        inv["reserved"]["2"] = 2
        self.assertEqual(available(inv, 2), 0)
        with self.assertRaises(ProtocolError):
            reservations.acquire(inv, "maintenance",
                                 [{"index": 2, "count": 1, "item_id": 200}])


class CoordinationAndEventRouting(unittest.TestCase):
    def test_single_domain_event_handlers(self):
        self.assertFalse(WORLD_KINDS & BATTLE_KINDS)
        self.assertFalse(WORLD_KINDS & SESSION_KINDS)
        self.assertFalse(BATTLE_KINDS & SESSION_KINDS)
        state = State()
        state.apply({"type": "login_result", "result": 0})
        self.assertEqual(state.phase, "authenticated")
        state.player = {"role_id": 88, "scene": 1, "x": 2, "y": 3}
        state.apply({"type": "battle_start", "stage": 1, "fight_number": 1, "units": []})
        self.assertTrue(state.battle["active"])
        state.apply({"type": "winner", "side": 1})
        self.assertFalse(state.battle["active"])

    def test_maintenance_and_crafting_gates_preserve_stop_operations(self):
        state = State(phase="world_ready")
        state.maintenance["pending"] = {"index": 1}
        self.assertIn("戰後", command_reason(state, {"type": "start_roaming"}))
        self.assertEqual(command_reason(state, {"type": "stop_auto_battle"}), "")
        state.maintenance["pending"] = None
        state.crafting["pending"] = {"action": "start"}
        self.assertIn("製作", command_reason(state, {"type": "field_item"}))
        self.assertIn("製作", reason(state, "expedition"))
        state.crafting["pending"] = None
        state.auto_battle["enabled"] = True
        self.assertEqual(reason(state, "expedition"), "")

    def test_network_layer_rejects_during_maintenance_without_sending(self):
        logic, state = SessionLogic(), State(phase="world_ready")
        logic.world_acknowledged = True
        state.maintenance["uncertain"] = True
        with self.assertRaises(ProtocolError):
            logic.command({"type": "start_expedition", "settings": {}}, state)
        with self.assertRaises(ProtocolError):
            logic.command({"type": "instance_refresh", "mode": "main"}, state)


class FieldSupplyReservation(unittest.TestCase):
    def make(self):
        state = State(phase="world_ready")
        state.player = {"role_id": 1}
        state.inventory = inventory()
        plan = {"bag_index": 1, "item_id": 100, "resource": "hp",
                "resource_reservations": [{"index": 1, "item_id": 100, "count": 1}]}
        target = {"col": 3, "row": 1, "pid": 1, "npc_index": 0, "hp": 10}
        return state, plan, target

    def test_field_heal_keeps_exclusive_hold_until_both_replies(self):
        state, plan, target = self.make()
        supply = FieldSupply()
        supply.begin(state, plan, target, now=0)
        self.assertEqual(available(state.inventory, 1), 0)
        self.assertEqual(state.inventory["reserved"]["1"], 1)
        # Exercise the authoritative bag deduction, not a guessed spend.
        state.apply({"type": "bag_delete", "index": 1, "count": 1})
        supply.observe({"type": "bag_delete", "index": 1, "count": 1}, state)
        supply.pending["restored"] = True
        with patch("wlre.services.items.field_supply.field_context",
                   return_value=({"battle_units": {"3:1": target}}, target)):
            response = supply.tick(state, now=1)
        self.assertEqual(response["status"], "confirmed")
        self.assertFalse(state.inventory.get("holds", {}).get("field_supply"))
        self.assertEqual(available(state.inventory, 1), 2)

    def test_timeout_marks_hold_uncertain_and_disallows_retry(self):
        state, plan, target = self.make()
        supply = FieldSupply()
        supply.begin(state, plan, target, now=0)
        with patch("wlre.services.items.field_supply.field_context",
                   return_value=({"battle_units": {"3:1": target}}, target)):
            response = supply.tick(state, now=16)
        self.assertEqual(response["status"], "uncertain")
        self.assertEqual(available(state.inventory, 1), 0)
        self.assertTrue(state.inventory["holds"]["field_supply"][0]["uncertain"])
        with self.assertRaises(ProtocolError):
            supply.check()


if __name__ == "__main__":
    unittest.main()
