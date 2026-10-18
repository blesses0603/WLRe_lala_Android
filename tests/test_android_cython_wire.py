"""Phase 04 reference vectors run cheaply without a Cython/Android build."""
import unittest
from unittest.mock import patch

from tools.android_cython_wire import EXPORTS, ROOT, SOURCE, probe_package, snapshot
from wlre.network import wire


class WireNativePilotTests(unittest.TestCase):
    def test_pure_python_wire_contract_is_frozen_before_native_port(self):
        result = snapshot(wire)
        self.assertEqual(result["exports"], [True] * len(EXPORTS))
        self.assertTrue(result["packet_equality"])
        self.assertEqual(result["packet_body"], "3f070100")
        self.assertEqual(result["encoded"], "696ba9ad92aaacad")
        self.assertEqual(result["other_xor"], "c4c604003f070100")
        self.assertEqual(result["split_frames"], ["3f070100", "060104020806"])
        self.assertEqual(result["decoded_text"], "AB")
        self.assertEqual(result["reader_numbers"], [1, 2, 3])
        self.assertEqual(result["writer"], "01341221436587")

    def test_protocol_failures_remain_strict(self):
        failures = snapshot(wire)["errors"]
        self.assertEqual(len(failures), 10)
        self.assertEqual(set(name for name, _ in failures.values()), {"ProtocolError"})
        self.assertEqual(failures["invalid_unicode"][1], "invalid UTF-16LE string")
        self.assertEqual(failures["too_long"][1], "body exceeds uint16 length")
        self.assertIn("bad frame magic", failures["bad_magic"][1])
        self.assertIn("incomplete final frame", failures["incomplete_frame"][1])

    def test_host_probe_refuses_false_native_claim(self):
        class Result:
            stdout = '{"native": false, "result": {}}'
        with patch("tools.android_cython_wire.subprocess.run", return_value=Result()):
            with self.assertRaisesRegex(RuntimeError, "wrong backend"):
                probe_package(ROOT, expect_native=True)

    def test_pilot_does_not_change_android_build_settings(self):
        self.assertTrue(SOURCE.is_file())
        spec = ROOT / "buildozer.spec"
        if spec.is_file():
            contents = spec.read_text(encoding="utf-8")
            self.assertIn("android.minapi = 31", contents)
            self.assertIn("android.archs = arm64-v8a", contents)


if __name__ == "__main__":
    unittest.main()
