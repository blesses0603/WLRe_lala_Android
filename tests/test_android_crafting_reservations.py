"""Android crafting reservations: packet acknowledgement is not material consumption.

These tests exercise the shared registry, the same manual/plan entry path, and
fail-closed handling of unconfirmed responses without contacting a game server.
"""
import copy
import unittest
from unittest.mock import patch

from wlre.core.state import State
from wlre.network.client import SessionLogic
from wlre.network.wire import Packet, ProtocolError
from wlre.services.items import reservations
from wlre.services.items.combat_resources import available
from wlre.services.items.crafting import Crafting


RECIPE_ID = 23456
MAT_ID = 500


def fixture():
    state = State(phase="world_ready")
    state.player = {"role_id": 1234, "scene": 12000, "x": 0, "y": 0}
    state.crafting.update(ready=True)
    state.inventory.update(ready=True, reliable=True, capacity=50,
                           items={"1": {"index": 1, "item_id": MAT_ID,
                                        "count": 5, "serial": 111,
                                        "serial_version": 1}},
                           reserved={})
    return state, Crafting()


def send_add(service, state):
    recipe = {"item_id": RECIPE_ID, "seconds": 60}
    allocations = [{"index": 1, "item_id": MAT_ID, "count": 2,
                    "before": 5, "serial": 111}]
    with patch("wlre.services.items.crafting.recipe_plan",
               return_value=(recipe, allocations, Packet(64, 1, b"\x01"))):
        result = service.command(state, {"action": "add",
                                         "item_id": RECIPE_ID, "count": 1}, now=0)
    return result


def ack(service, state):
    service.observe({"type": "craft_added",
                     "row": {"index": 1, "item_id": RECIPE_ID,
                             "count": 1, "elapsed": 0, "base_time": 60}},
                    state, now=1)


class CraftingSharedHoldTests(unittest.TestCase):
    def test_add_acquires_exclusive_identity_and_quantity_before_packet(self):
        state, service = fixture()
        packets = send_add(service, state)
        self.assertEqual([(p.main, p.sub) for p in packets], [(64, 1)])
        hold, = state.inventory["holds"]["crafting"]
        self.assertEqual(hold["index"], "1")
        self.assertEqual(hold["identity"], [MAT_ID, 111, 1])
        self.assertEqual((hold["count"], hold["remaining"]), (2, 2))
        self.assertEqual(state.inventory["reserved"]["1"], 2)
        self.assertEqual(available(state.inventory, 1), 0)
        with self.assertRaises(ProtocolError):
            reservations.acquire(state.inventory, "battle",
                                 [{"index": 1, "item_id": MAT_ID, "count": 1}])

    def test_ack_without_material_deduction_never_confirms(self):
        state, service = fixture()
        send_add(service, state)
        ack(service, state)
        self.assertIsNotNone(service.pending)
        self.assertEqual(state.crafting["pending"], "add")
        self.assertEqual(available(state.inventory, 1), 0)

    def test_confirm_requires_both_ack_and_authoritative_deduction(self):
        state, service = fixture()
        send_add(service, state)
        state.apply({"type": "bag_delete", "index": 1, "count": 2})
        service.observe({"type": "bag_delete", "index": 1, "count": 2},
                        state, now=1)
        self.assertIsNotNone(service.pending)
        ack(service, state)
        self.assertIsNone(service.pending)
        self.assertIsNone(state.crafting["pending"])
        self.assertFalse(state.inventory.get("holds", {}).get("crafting"))
        self.assertEqual(available(state.inventory, 1), 3)
        self.assertEqual(state.inventory["reserved"].get("1", 0), 0)

    def test_changed_serial_or_missing_partial_stack_stays_pending(self):
        for mode in ("serial", "missing"):
            with self.subTest(mode=mode):
                state, service = fixture()
                send_add(service, state)
                if mode == "serial":
                    state.inventory["items"]["1"]["serial"] = 999
                else:
                    state.inventory["items"].pop("1")
                ack(service, state)
                self.assertIsNotNone(service.pending)
                self.assertEqual(available(state.inventory, 1), 0)
                self.assertTrue(state.inventory["holds"]["crafting"])

    def test_snapshot_preserves_exclusive_hold_while_ack_pending(self):
        state, service = fixture()
        send_add(service, state)
        old = state.inventory
        fresh = copy.deepcopy(old)
        fresh["holds"] = {}
        fresh["reserved"] = {}
        reservations.refreshed(old, fresh)
        state.inventory = fresh
        self.assertEqual(available(state.inventory, 1), 0)
        self.assertEqual(state.inventory["holds"]["crafting"][0]["remaining"], 2)
        ack(service, state)
        self.assertIsNotNone(service.pending)

    def test_timeout_marks_unknown_materials_uncertain_no_retry(self):
        state, service = fixture()
        send_add(service, state)
        self.assertEqual(service.tick(state, now=16), [])
        self.assertIsNone(service.pending)
        self.assertFalse(state.inventory["reliable"])
        self.assertTrue(state.crafting["uncertain"])
        self.assertFalse(state.crafting["auto_continue"])
        self.assertTrue(state.inventory["holds"]["crafting"][0]["uncertain"])
        self.assertEqual(available(state.inventory, 1), 0)
        self.assertEqual(service.tick(state, now=100), [])
        with self.assertRaises(ProtocolError):
            send_add(service, state)

    def test_explicit_failure_can_release_because_server_rejected(self):
        state, service = fixture()
        send_add(service, state)
        service.observe({"type": "craft_failed", "reason": "伺服器拒絕"},
                        state, now=1)
        self.assertIsNone(service.pending)
        self.assertFalse(state.inventory.get("holds", {}).get("crafting"))
        self.assertEqual(available(state.inventory, 1), 5)

    def test_multi_item_conflict_rejects_atomically_without_pending(self):
        state, service = fixture()
        state.inventory["items"]["2"] = {"index": 2, "item_id": 501,
                                         "count": 3, "serial": 222}
        reservations.acquire(state.inventory, "expedition",
                             [{"index": 2, "item_id": 501, "count": 1}],
                             exclusive=True)
        baseline = reservations.checkpoint(state.inventory)
        allocations = [{"index": 1, "item_id": MAT_ID,
                        "count": 2, "before": 5, "serial": 111},
                       {"index": 2, "item_id": 501,
                        "count": 1, "before": 3, "serial": 222}]
        with patch("wlre.services.items.crafting.recipe_plan",
                   return_value=({"item_id": RECIPE_ID, "seconds": 60},
                                 allocations, Packet(64, 1, b"\x01"))):
            with self.assertRaises(ProtocolError):
                service.command(state, {"action": "add",
                                        "item_id": RECIPE_ID, "count": 1}, now=0)
        self.assertIsNone(service.pending)
        self.assertEqual(state.crafting["pending"], None)
        self.assertEqual(reservations.checkpoint(state.inventory), baseline)

    def test_manual_and_automatic_plan_obey_shared_coordination_gate(self):
        state, service = fixture()
        state.expedition["enabled"] = True
        with self.assertRaisesRegex(ProtocolError, "遠征"):
            send_add(service, state)
        self.assertFalse(state.inventory.get("holds", {}).get("crafting"))
        local = service.plan(state)
        local["rows"] = [{"item_id": RECIPE_ID, "count": 1}]
        with self.assertRaisesRegex(ProtocolError, "遠征"):
            service.command(state, {"action": "plan_start",
                                    "revision": local["revision"]}, now=0)
        self.assertFalse(local["enabled"])
        state.expedition["enabled"] = False
        state.maintenance["pending"] = {"index": 1}
        local["enabled"] = True
        state.crafting["auto_continue"] = True
        self.assertEqual(service.tick(state, now=1), [])
        self.assertIsNone(service.pending)
        self.assertIn("戰後", local["status"])

    def test_disconnect_freezes_crafting_hold_and_disables_continuation(self):
        state, _ = fixture()
        logic = SessionLogic()
        send_add(logic.crafting, state)
        logic.disconnect(state)
        self.assertFalse(state.inventory["reliable"])
        self.assertTrue(state.inventory["holds"]["crafting"][0]["uncertain"])
        self.assertEqual(available(state.inventory, 1), 0)
        self.assertIsNone(logic.crafting.pending)
        self.assertFalse(state.crafting["auto_continue"])
        with self.assertRaises(ProtocolError):
            reservations.acquire(state.inventory, "alchemy",
                                 [{"index": 1, "item_id": MAT_ID, "count": 1}])


if __name__ == "__main__":
    unittest.main()
