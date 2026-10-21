"""Android/Desktop v0.5.6 shared hold registry and S31 disconnect regressions.

All exchange packets below are local fixtures; no live account or rewards.
"""
import unittest
from unittest.mock import Mock, patch

from wlre.core.state import State
from wlre.network.client import run_client
from wlre.network.protocol import decode
from wlre.network.wire import Packet, ProtocolError, Writer, encode
from wlre.services.expedition import Expedition
from wlre.services.items import reservations
from wlre.services.items.combat_resources import (
    CAT, apply_live, available, reserve
)
from wlre.services.items.alchemy import AutoAlchemy, material_problem, category
from wlre.core.inventory_updates import STACKABLE


def bag_item(sid, count, serial):
    return {"item_id": sid, "count": count, "serial": serial, "serial_version": 1}


def alchemy_case():
    state = State()
    state.player = {"role_id": 42, "scene": 12000, "x": 0, "y": 0}
    state.inventory.update(ready=True, reliable=True, capacity=200)
    rows = []
    for item_id in CAT["items"]:
        item = bag_item(int(item_id), 20, 100 + len(rows))
        item["index"] = len(rows) + 1
        if STACKABLE.get(str(item_id)) and not material_problem(item) and category(item) == "normal":
            rows.append(item)
        if len(rows) == 2:
            break
    if len(rows) != 2:
        raise AssertionError("official materials fixture missing")
    for row in rows:
        state.inventory["items"][str(row["index"])] = row
    command = {"type": "start_alchemy", "runs": 2,
               "materials": [{"index": r["index"], "item_id": r["item_id"],
                              "count": 1} for r in rows]}
    return state, AutoAlchemy(), command


def expedition_case():
    state = State(phase="world_ready")
    state.expedition.update(
        ready=True, outpost_ready=True, level=1,
        roles={"1": {"index": 1, "npc_id": 101, "state": 0, "faith": 70,
                      "stats": {"level": 30, "degree": 0, "str": 10,
                                "con": 10, "int": 10, "wis": 10,
                                "agi": 10, "potential": 0}}},
        quests={"1": 2},
        teams={"1": {"index": 1, "quest": 0, "members": [0, 0, 0, 0]}})
    state.inventory.update(ready=True, reliable=True,
                           capacity=20, items={"3": bag_item(34014, 5, 25)})
    catalog = {"levels": {"1": {"teams": 1, "difficulty": 3, "reduction": 0}},
               "tasks": {"2": {"id": 2, "area": 2, "minutes": 360,
                               "faith_cost": 20, "difficulty": 1,
                               "condition": [0, 0, 0]}}}
    service = Expedition(catalog)
    service.start(state, {"min_hours": 5, "faith_min": 80,
                          "item_id": 34014, "min_success": 0})
    return state, service


class SharedReservationsIntegration(unittest.TestCase):
    def test_battle_hold_survives_refresh_until_authoritative_deduction(self):
        state = State()
        sid = next(int(sid) for sid, value in STACKABLE.items() if value)
        state.inventory.update(ready=True, reliable=True,
                               items={"1": bag_item(sid, 3, 11)})
        reserve(state, [{"index": 1, "item_id": sid, "count": 1}])
        self.assertEqual(state.inventory["holds"]["battle"][0]["identity"][:2],
                         [sid, 11])
        self.assertEqual(available(state.inventory, 1), 2)
        apply_live(state, {"type": "bag_snapshot", "capacity": 20,
                           "items": [{**bag_item(sid, 3, 11), "index": 1}]})
        self.assertTrue(state.inventory["reliable"])
        self.assertEqual(available(state.inventory, 1), 2)
        apply_live(state, {"type": "bag_delete", "index": 1, "count": 1})
        self.assertNotIn("battle", state.inventory.get("holds", {}))
        self.assertEqual(available(state.inventory, 1), 2)

    def test_battle_registration_is_atomic_across_other_services(self):
        state = State()
        state.inventory.update(ready=True, reliable=True,
                               items={"1": bag_item(100, 3, 11),
                                      "2": bag_item(200, 2, 22)})
        reservations.acquire(state.inventory, "maintenance",
                             [{"index": 2, "count": 1, "item_id": 200}],
                             exclusive=True)
        before = reservations.checkpoint(state.inventory)
        with self.assertRaises(ProtocolError):
            reserve(state, [{"index": 1, "item_id": 100, "count": 1},
                            {"index": 2, "item_id": 200, "count": 1}])
        self.assertEqual(reservations.checkpoint(state.inventory), before)

    def test_alchemy_confirmed_release_keeps_only_real_remaining_count(self):
        state, alchemy, command = alchemy_case()
        self.assertEqual(len(alchemy.start(state, command, now=0)), 1)
        self.assertEqual(len(state.inventory["holds"]["alchemy"]), 2)
        self.assertEqual(len(state.inventory["alchemy_slots"]), 2)
        original = [{**v} for v in state.inventory["items"].values()]
        apply_live(state, {"type": "bag_snapshot", "capacity": 200, "items": original})
        self.assertTrue(state.inventory["reliable"])
        self.assertEqual(len(state.inventory["holds"]["alchemy"]), 2)
        rows = list(alchemy.pending["consumption"])
        for row in rows:
            event = {"type": "bag_delete", "index": row["index"],
                     "count": row["count"]}
            apply_live(state, event)
            alchemy.observe(event, state, now=1)
        output = next(int(sid) for sid, value in STACKABLE.items()
                      if value and int(sid) not in {v["item_id"] for v in state.inventory["items"].values()})
        alchemy.observe({"type": "alchemy_result", "item_id": output,
                         "count": 1}, state, now=1)
        event = {"type": "bag_add", "source": 3,
                 "item": {"index": 9, "item_id": output,
                          "count": 1, "serial": 777}}
        apply_live(state, event)
        self.assertTrue(state.inventory["reliable"])
        alchemy.observe(event, state, now=1)
        self.assertIsNone(alchemy.pending)
        self.assertEqual(state.alchemy["completed"], 1)
        self.assertFalse(state.inventory.get("holds", {}).get("alchemy"))
        self.assertEqual(state.inventory["alchemy_slots"], [])

    def test_alchemy_failure_and_timeout_do_not_release_unknown_items(self):
        for kind in ("alchemy_space_error", "timeout"):
            with self.subTest(kind=kind):
                state, alchemy, command = alchemy_case()
                alchemy.start(state, command, now=0)
                if kind == "timeout":
                    self.assertEqual(alchemy.tick(state, now=16), [])
                else:
                    alchemy.observe({"type": "alchemy_space_error"}, state, now=1)
                self.assertFalse(state.inventory["reliable"])
                self.assertFalse(state.alchemy["enabled"])
                self.assertTrue(state.inventory["holds"]["alchemy"])
                self.assertTrue(all(row["uncertain"] for row in
                                    state.inventory["holds"]["alchemy"]))
                self.assertEqual(available(state.inventory, 1), 0)

    def test_expedition_faith_hold_release_only_after_two_confirmations(self):
        state, expedition = expedition_case()
        packet, = expedition.tick(state, 10)
        self.assertEqual((packet.main, packet.sub), (31, 27))
        self.assertEqual(state.inventory["expedition_slots"], ["3"])
        self.assertEqual(available(state.inventory, 3), 0)
        event = {"type": "outpost_faith", "index": 1, "faith": 80, "show": 0}
        state.apply(event)
        expedition.observe(event, state)
        self.assertIsNotNone(expedition.pending)
        event = {"type": "bag_delete", "index": 3, "count": 2}
        state.apply(event)
        expedition.observe(event, state)
        self.assertIsNone(expedition.pending)
        self.assertEqual(state.inventory["expedition_slots"], [])
        self.assertEqual(available(state.inventory, 3), 3)

    def test_expedition_faith_timeout_keeps_unknown_hold_no_resend(self):
        state, expedition = expedition_case()
        self.assertEqual(len(expedition.tick(state, 10)), 1)
        self.assertEqual(expedition.tick(state, 31), [])
        self.assertTrue(state.expedition["uncertain"])
        self.assertFalse(state.expedition["enabled"])
        self.assertTrue(state.inventory["holds"]["expedition"][0]["uncertain"])
        self.assertEqual(available(state.inventory, 3), 0)
        self.assertEqual(expedition.tick(state, 100), [])
        self.assertFalse(State().inventory.get("holds"))


class DisconnectAndClaimSafety(unittest.TestCase):
    def test_disconnected_pending_reward_is_never_reported_as_confirmed(self):
        from wlre.network.client import SessionLogic
        state = State(phase="world_ready")
        state.expedition.update(enabled=True, pending="claim", uncertain=False)
        logic = SessionLogic()
        logic.expedition.pending = {"kind": "claim", "index": 1, "quest": 2,
                                    "due": 20, "before": {}, "expected": {}}
        logic.disconnect(state)
        self.assertTrue(state.expedition["uncertain"])
        self.assertFalse(state.expedition["enabled"])
        self.assertEqual(state.expedition["pending"], "claim")
        self.assertIsNotNone(logic.expedition.pending)
        self.assertEqual(logic.expedition.tick(state, 200), [])
        self.assertEqual(state.expedition["claimed"], 0)

    def test_disconnect_freezes_every_unconfirmed_bag_owner(self):
        from wlre.network.client import SessionLogic
        state = State(phase="world_ready")
        state.inventory.update(ready=True, reliable=True,
                               items={"1": bag_item(34014, 4, 5)})
        reservations.acquire(state.inventory, "expedition",
                             [{"index": 1, "item_id": 34014, "count": 2}],
                             exclusive=True)
        logic = SessionLogic()
        logic.expedition.pending = {"kind": "faith", "index": 1, "due": 30}
        logic.disconnect(state)
        self.assertFalse(state.inventory["reliable"])
        self.assertTrue(state.inventory["holds"]["expedition"][0]["uncertain"])
        self.assertEqual(available(state.inventory, 1), 0)
        self.assertEqual(state.inventory["expedition_slots"], ["1"])
        self.assertTrue(state.expedition["uncertain"])
        with self.assertRaises(ProtocolError):
            reservations.acquire(state.inventory, "battle",
                                 [{"index": 1, "item_id": 34014, "count": 1}])

    def test_reward_result_then_quest_refresh_waits_for_bag_before_redeploy(self):
        state, expedition = expedition_case()
        award = {"kind": 10, "id": 34014, "value": 2}
        expedition.catalog["tasks"]["2"].update(
            rewards=[award], special_reward={"kind": 0, "id": 0, "value": 0})
        state.expedition["roles"]["1"]["state"] = 1
        state.expedition["teams"]["1"].update(
            quest=2, members=[101, 0, 0, 0], due=9)
        packet, = expedition.tick(state, 10)
        self.assertEqual((packet.main, packet.sub), (31, 16))
        result = (Writer().u8(1).u8(1).u16(0).u16(0)
                  .u8(10).u32(34014).u32(2).build())
        events = [
            decode(Packet(31, 16, result)),
            decode(Packet(31, 19,
                   b"".join(Writer().u8(i).u16(0).build()
                            for i in range(1, 51)) + bytes([1]))),
        ]
        for event in events:
            state.apply(event)
            expedition.observe(event, state)
            self.assertIsNotNone(expedition.pending)
            self.assertEqual(expedition.tick(state, 11), [])
        event = {"type": "bag_add", "item":
                 {"index": 4, "item_id": 34014, "count": 2, "serial": 88}}
        state.apply(event)
        expedition.observe(event, state)
        self.assertIsNone(expedition.pending)
        self.assertEqual(state.expedition["claimed"], 1)


class ExpeditionWireCompatibility(unittest.TestCase):
    def test_s31_19_mandatory_flag_and_opaque_s31_15_ack(self):
        entries = b"".join(Writer().u8(i).u16(i if i <= 2 else 0).build()
                           for i in range(1, 51))
        for flag in (0, 1):
            message = decode(Packet(31, 19, entries + bytes([flag])))
            self.assertEqual(message["show"], bool(flag))
            self.assertEqual(len(message["quests"]), 50)
        for invalid in (entries, entries + b"\x00\x01"):
            with self.assertRaises(ProtocolError):
                decode(Packet(31, 19, invalid))
        for tail in (b"", b"\x02", b"\xa5\x04\x7f"):
            message = decode(Packet(31, 15, tail))
            self.assertEqual(message, {"type": "expedition_started",
                                       "extension_bytes": len(tail)})

    def test_reward_then_quest_refresh_and_start_ack_do_not_disconnect(self):
        reward = (Writer().u8(1).u8(1).u16(0).u16(0)
                  .u8(10).u32(34014).u32(2).build())
        entries = b"".join(Writer().u8(i).u16(0).build()
                           for i in range(1, 51)) + b"\x01"
        connection = Mock()
        connection.__enter__ = Mock(return_value=connection)
        connection.__exit__ = Mock(return_value=False)
        connection.recv.side_effect = [
            encode(Packet(31, 16, reward), 0),
            encode(Packet(31, 19, entries), 0),
            encode(Packet(31, 15, b"\x02\x03"), 0),
            b"",
        ]
        events = []
        with patch("wlre.network.client.socket.create_connection",
                   return_value=connection):
            state = run_client("fixture.invalid", 1,
                               {"rx_xor": 0, "tx_xor": 0}, events.append,
                               duration=None)
        self.assertEqual(state.phase, "disconnected")
        self.assertEqual([e["type"] for e in events
                          if e.get("type", "").startswith("expedition_")],
                         ["expedition_result", "expedition_quests",
                          "expedition_started"])
        self.assertEqual([e["reason"] for e in events
                          if e["type"] == "connection_closed"], ["server_closed"])
        self.assertFalse(any(e.get("reason") == "client_error" for e in events))
        self.assertFalse(any("packet_main" in e for e in events))


if __name__ == "__main__":
    unittest.main()
