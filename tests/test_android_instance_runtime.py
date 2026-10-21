"""Android batch port regression: verified read-only instance and S51 core."""
import unittest

from android_app.features import GAME_COMMANDS, checked_command, project
from wlre.core.state import State
from wlre.network.client import SessionLogic
from wlre.network.instances import list_request, member_request
from wlre.network.protocol import decode
from wlre.network.wire import Packet, ProtocolError, Writer
from wlre.services.battle.attribute_points import allocation, baseline


def main_room():
    name = "房主".encode("utf-16le")
    guild = "團".encode("utf-16le")
    return (Writer().u8(1).u16(210).u8(len(name)).raw(name)
            .u8(3).u8(len(guild)).raw(guild).u8(1).u16(55).build())


class InstanceReadOnlyCore(unittest.TestCase):
    def test_server_main_room_is_authoritative_and_isolated(self):
        first, second = State(), State()
        first.apply(decode(Packet(85, 1, main_room())))
        self.assertTrue(first.instances["main"]["ready"])
        self.assertEqual(first.instances["main"]["rooms"][0]["manager"], "房主")
        self.assertFalse(second.instances["main"]["ready"])
        first.apply(decode(Packet(85, 5, Writer().u8(1).u8(1).u16(210).u8(2).u32(345).build())))
        self.assertEqual(first.instances["main"]["room"]["room_id"], 210)
        first.apply(decode(Packet(85, 4, Writer().u16(210).u8(2).u32(345).u32(456).build())))
        self.assertEqual(len(first.instances["main"]["members"]), 2)
        first.apply(decode(Packet(85, 5, b"\x02")))
        self.assertIsNone(first.instances["main"]["room"])
        snap = project(first.snapshot())
        self.assertIn("instances", snap)
        snap["instances"]["main"]["rooms"].clear()
        self.assertEqual(len(first.instances["main"]["rooms"]), 1)

    def test_coop_room_list_and_invalid_lengths(self):
        room = Writer().u16(1).u8(1).u8(2).u8(7).u16(99).u8(4).u8(2).u32(345).build()
        state = State()
        state.apply(decode(Packet(186, 17, room)))
        self.assertEqual(state.instances["coop"]["rooms"][0]["host_id"], 345)
        for packet in (Packet(85, 1, b"\x01\x00"),
                       Packet(186, 17, b"\x01"),
                       Packet(85, 2, b"\x00\x02")):
            with self.subTest(packet=packet), self.assertRaises(ProtocolError):
                decode(packet)

    def test_explicit_queries_and_allowlist_requires_verified_actions(self):
        logic = SessionLogic()
        state = State(phase="world_ready")
        logic.world_acknowledged = True
        self.assertEqual(logic.command({"type":"instance_refresh","mode":"main"}, state), [Packet(85, 1)])
        self.assertEqual(logic.command({"type":"instance_refresh","mode":"coop"}, state), [Packet(186, 17)])
        self.assertEqual(checked_command({"type":"instance_refresh","mode":"main"}),
                         {"type":"instance_refresh","mode":"main"})
        state.instances["main"]["room"] = {"room_id":210}
        self.assertEqual(logic.command({"type":"instance_members","mode":"main","room_id":210}, state),
                         [Packet(85, 4, Writer().u16(210).build())])
        for bad in ({"type":"instance_refresh","mode":"invalid"},
                    {"type":"instance_members","mode":"main","room_id":211},
                    {"type":"instance_refresh","mode":"main","payload":"hidden"}):
            with self.assertRaises((ValueError, KeyError, TypeError)):
                logic.command(bad, state)
        state.battle["active"] = True
        with self.assertRaises(ProtocolError):
            logic.command({"type":"instance_refresh","mode":"main"}, state)
        for name in ("instance_create","instance_join","instance_leave",
                     "instance_coop_standby","instance_start","instance_enter",
                     "instance_reward_claim","instance_reward_cancel",
                     "instance_auto_reward","allocate_points"):
            self.assertIn(name, GAME_COMMANDS)
        for name in ("instance_claim","instance_standby","allocate_attributes",
                     "npc_start","npc_choose"):
            self.assertNotIn(name, GAME_COMMANDS)
            with self.assertRaises(ValueError):
                checked_command({"type":name})

    def test_malformed_s51_packet_does_not_disconnect(self):
        event = decode(Packet(51, 1, b"\x01\x02\x03\x04\x05\x06\x07\x08"))
        self.assertEqual(event["type"], "battle_attribute_invalid")
        self.assertEqual(event["complete_records"], 1)
        self.assertEqual(event["trailing_bytes"], 1)
        state = State()
        state.apply(event)
        self.assertEqual(state.packet_count, 1)
        self.assertEqual(state.battle_count, 0)

    def test_attribute_baseline_and_no_mobile_allocation(self):
        stats = {"int":4,"str":5,"con":6,"agi":7,"wis":8,"attribute_potential":2}
        packet, expected = allocation(stats, {"int":1}, dict(stats))
        self.assertEqual((packet.main,packet.sub), (8, 1))
        self.assertEqual(expected["attribute_potential"], 1)
        self.assertEqual(baseline(stats), stats)
        with self.assertRaises(ProtocolError):
            allocation(stats, {"int":1}, {**stats, "int":1})
        with self.assertRaises(ValueError):
            checked_command({"type":"allocate_attributes","amount":1})

    def test_connection_error_is_redacted_to_code_location(self):
        from wlre.network.connection_health import ConnectionHealth
        from wlre.core.diagnostics import safe_exception_location
        def raise_sample():
            raise ValueError("private-credential-should-not-appear")
        try:
            raise_sample()
        except ValueError as exc:
            kind, frames = safe_exception_location(type(exc), exc.__traceback__)
            self.assertEqual(kind, "ValueError")
            self.assertIn("raise_sample", frames)
            self.assertNotIn("private-credential", frames)
            messages = []
            obj = ConnectionHealth(messages.append, clock=lambda: 25, wall=lambda: 10)
            obj.close("client_error", exc, error_packet=(51, 1), error_stage="decode")
            status = messages[-1]
            self.assertEqual(status["packet_main"], 51)
            self.assertEqual(status["packet_sub"], 1)
            self.assertEqual(status["packet_stage"], "decode")
            self.assertNotIn("private-credential", str(status))


if __name__ == "__main__":
    unittest.main()
