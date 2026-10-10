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
from parser.arp_parser import parse_arp as parse_arp_compat
from parser.interface_parser import parse_interface as parse_interface_compat
from parser.ping_parser import parse_ping as parse_ping_compat
from parser.route_parser import parse_route as parse_route_compat
from parser.tracert_parser import parse_tracert as parse_tracert_compat


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

    def test_route_count_zero_is_a_missing_route(self) -> None:
        for header in ("Summary Count : 0", "Route Count : 0"):
            facts = parse_route(header, {})
            self.assertEqual(facts, {"route_found": False})

    def test_interface_extracts_states(self) -> None:
        text = "GE0/0/1 current state : DOWN\nLine protocol current state : DOWN"
        facts = parse_interface(text, {})
        self.assertEqual(facts["interface"], "GigabitEthernet0/0/1")
        self.assertEqual(facts["physical_status"], "DOWN")
        self.assertEqual(facts["protocol_status"], "DOWN")

    def test_full_route_table_selects_longest_matching_prefix(self) -> None:
        text = (
            "Routing Tables: Public\nDestinations : 3 Routes : 3\n"
            "0.0.0.0/0 Static 60 0 RD 10.0.12.2 GE0/0/0\n"
            "192.168.3.0/24 Static 60 0 RD 10.0.23.2 GE0/0/1\n"
            "192.168.3.1/32 Static 60 0 RD 10.0.23.3 GE0/0/2"
        )
        facts = parse_route(text, {"destination": "192.168.3.1"})
        self.assertEqual(facts["destination"], "192.168.3.1/32")
        self.assertEqual(facts["next_hop"], "10.0.23.3")
        default = parse_route(text, {"destination": "203.0.113.1"})
        self.assertEqual(default["destination"], "0.0.0.0/0")

    def test_complete_route_table_can_prove_target_route_missing(self) -> None:
        text = (
            "Routing Tables: Public\nDestinations : 1 Routes : 1\n"
            "10.0.12.0/24 Direct 0 0 D 10.0.12.2 GE0/0/0"
        )
        self.assertEqual(
            parse_route(text, {"destination": "192.168.3.1"}),
            {"route_found": False},
        )

    def test_incomplete_route_table_cannot_prove_route_missing(self) -> None:
        outputs = [
            "",
            "Routing Tables: Public\nDestinations : 1 Routes : 1\nmalformed entry",
            "Routing Tables: Public\nDestinations : 2 Routes : 2\n"
            "10.0.12.0/24 Direct 0 0 D 10.0.12.2 GE0/0/0",
            "10.0.12.0/24 Direct 0 0 D 10.0.12.2 GE0/0/0",
        ]
        for text in outputs:
            with self.subTest(text=text):
                result = parse_cli_output(
                    "CHECK_ROUTE", text, context={"destination": "192.168.3.1"}
                )
                self.assertFalse(result["success"])
                self.assertEqual(result["facts"], {})

    def test_interface_accepts_administratively_down(self) -> None:
        text = (
            "GigabitEthernet0/0/1 current state : Administratively DOWN\n"
            "Line protocol current state : DOWN"
        )
        facts = parse_interface(text, {})
        self.assertEqual(facts["physical_status"], "DOWN")

    def test_arp_reports_target_entry(self) -> None:
        text = "192.168.3.10  00e0-fc00-0003  20  D-0  GE0/0/1"
        facts = parse_arp(text, {"target_ip": "192.168.3.10"})
        self.assertTrue(facts["entry_found"])

    def test_unknown_command_returns_parser_error(self) -> None:
        result = parse_cli_output("UNKNOWN", "", device="R2")
        self.assertFalse(result["success"])
        self.assertEqual(result["facts"], {})
        self.assertIn("Unsupported", result["error"])

    def test_unknown_vendor_returns_parser_error(self) -> None:
        result = parse_cli_output(
            "PING",
            "5 packet(s) transmitted\n0.00% packet loss",
            device="R2",
            vendor="cisco_ios",
        )
        self.assertFalse(result["success"])
        self.assertEqual(result["facts"], {})
        self.assertIn("Unsupported vendor", result["error"])

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

    def test_compatibility_entrypoints_use_unified_envelope(self) -> None:
        self.assertEqual(
            parse_ping_compat("5 packet(s) transmitted\n0.00% packet loss", "R1"),
            {
                "success": True,
                "device": "R1",
                "vendor": "huawei_vrp",
                "command_type": "PING",
                "facts": {"reachable": True, "packet_loss": 0},
                "error": None,
            },
        )
        route = parse_route_compat("Summary Count : 0", "R1")
        self.assertTrue(route["success"])
        self.assertEqual(route["facts"], {"route_found": False})

    def test_compatibility_entrypoints_preserve_parser_facts(self) -> None:
        interface = parse_interface_compat(
            "GE0/0/1 current state : UP\nLine protocol current state : UP", "R1"
        )
        self.assertEqual(interface["facts"]["interface"], "GigabitEthernet0/0/1")
        self.assertEqual(interface["facts"]["physical_status"], "UP")

        arp = parse_arp_compat(
            "10.0.0.2  00e0-fc00-0003  20  D-0  GE0/0/1",
            "R1",
            target_ip="10.0.0.2",
        )
        self.assertTrue(arp["facts"]["entry_found"])

        tracert = parse_tracert_compat(
            "1  10.0.0.2  10 ms  10 ms  10 ms\n2  *  *  *",
            "R1",
            context={"ip_to_device": {"10.0.0.2": "R2"}},
        )
        self.assertEqual(tracert["facts"]["suspect_device"], "R2")

    def test_compatibility_entrypoints_return_errors_without_raising(self) -> None:
        for parser in (
            parse_ping_compat,
            parse_interface_compat,
            parse_route_compat,
        ):
            result = parser("unexpected output", "R1")
            self.assertFalse(result["success"])
            self.assertEqual(result["facts"], {})
            self.assertIsInstance(result["error"], str)

        arp = parse_arp_compat("unexpected output", "R1", target_ip="10.0.0.2")
        self.assertFalse(arp["success"])
        self.assertEqual(arp["facts"], {})

        tracert = parse_tracert_compat("unexpected output", "R1")
        self.assertFalse(tracert["success"])
        self.assertEqual(tracert["facts"], {})
        self.assertIn("recognizable hops", tracert["error"])

    def test_compatibility_ping_empty_output_returns_error(self) -> None:
        result = parse_ping_compat("", "R1")
        self.assertFalse(result["success"])
        self.assertEqual(result["facts"], {})
        self.assertIsInstance(result["error"], str)


if __name__ == "__main__":
    unittest.main()
