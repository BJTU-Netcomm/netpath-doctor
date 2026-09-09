from __future__ import annotations

import unittest

from parser.huawei_vrp import (
    normalize_interface,
    parse_arp,
    parse_cli_output,
    parse_interface,
    parse_ping,
    parse_route,
    parse_tracert,
)


class HuaweiVrpParserTests(unittest.TestCase):
    def test_ping_packet_loss(self) -> None:
        facts = parse_ping("5 packet(s) transmitted\n100.00% packet loss", {})
        self.assertEqual(facts, {"reachable": False, "packet_loss": 100})

    def test_tracert_resolves_last_reachable_device(self) -> None:
        text = "1  10.0.12.2  10 ms  10 ms  10 ms\n2  *  *  *"
        facts = parse_tracert(text, {"ip_to_device": {"10.0.12.2": "R2"}})
        self.assertEqual(facts["last_reachable_ip"], "10.0.12.2")
        self.assertEqual(facts["suspect_device"], "R2")

    def test_route_extracts_next_hop_and_full_interface(self) -> None:
        text = "192.168.3.0/24 Static 60 0 RD 10.0.23.2 GE0/0/1"
        facts = parse_route(text, {})
        self.assertTrue(facts["route_found"])
        self.assertEqual(facts["next_hop"], "10.0.23.2")
        self.assertEqual(facts["out_interface"], "GigabitEthernet0/0/1")

    def test_interface_extracts_states(self) -> None:
        text = "GE0/0/1 current state : DOWN\nLine protocol current state : DOWN"
        facts = parse_interface(text, {})
        self.assertEqual(facts["interface"], "GigabitEthernet0/0/1")
        self.assertEqual(facts["physical_status"], "DOWN")
        self.assertEqual(facts["protocol_status"], "DOWN")

    def test_arp_reports_target_entry(self) -> None:
        text = "192.168.3.10  00e0-fc00-0003  20  D-0  GE0/0/1"
        facts = parse_arp(text, {"target_ip": "192.168.3.10"})
        self.assertTrue(facts["entry_found"])

    def test_unknown_command_returns_parser_error(self) -> None:
        result = parse_cli_output("UNKNOWN", "", device="R2")
        self.assertFalse(result["success"])
        self.assertEqual(result["facts"], {})
        self.assertIn("Unsupported", result["error"])

    def test_unrecognized_route_output_is_a_parser_error(self) -> None:
        result = parse_cli_output("CHECK_ROUTE", "unexpected output", device="R2")
        self.assertFalse(result["success"])
        self.assertIn("recognizable route", result["error"])

    def test_unrecognized_arp_output_is_a_parser_error(self) -> None:
        result = parse_cli_output(
            "CHECK_ARP",
            "unexpected output",
            device="R2",
            context={"target_ip": "192.168.3.10"},
        )
        self.assertFalse(result["success"])
        self.assertIn("zero-entry summary", result["error"])

    def test_normalize_interface_leaves_full_name_unchanged(self) -> None:
        self.assertEqual(
            normalize_interface("GigabitEthernet0/0/1"),
            "GigabitEthernet0/0/1",
        )


if __name__ == "__main__":
    unittest.main()
