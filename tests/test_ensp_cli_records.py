from __future__ import annotations

import unittest
from pathlib import Path

from parser.huawei_vrp import parse_cli_output


RECORDS = Path(__file__).resolve().parents[1] / "docs" / "cli_records"


def read_record(name: str) -> str:
    return (RECORDS / name).read_text(encoding="utf-8")


class EnspCliRecordTests(unittest.TestCase):
    """Parse captures from Li Mengyao's 46dae51 without contacting devices."""

    def test_normal_ping(self) -> None:
        result = parse_cli_output("RUN_PING", read_record("normal/normal_ping_R1.txt"), device="R1")
        self.assertTrue(result["success"])
        self.assertEqual(result["facts"], {"reachable": True, "packet_loss": 0})

    def test_route_missing_ping(self) -> None:
        result = parse_cli_output("RUN_PING", read_record("route_missing/route_missing_ping_R1.txt"), device="R1")
        self.assertTrue(result["success"])
        self.assertEqual(result["facts"], {"reachable": False, "packet_loss": 100})

    def test_tracert_captured_hops(self) -> None:
        result = parse_cli_output(
            "RUN_TRACERT", read_record("normal/normal_tracert_R1.txt"), device="R1",
            context={"ip_to_device": {"10.0.12.2": "R2", "10.0.23.2": "R3"}},
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["facts"]["hops"], [{"hop": 1, "ip": "10.0.12.2"}, {"hop": 2, "ip": "10.0.23.2"}])
        self.assertEqual(result["facts"]["last_reachable_device"], "R3")

    def test_normal_route_covers_host(self) -> None:
        result = parse_cli_output(
            "CHECK_ROUTE", read_record("normal/normal_route_R2.txt"), device="R2",
            context={"destination": "192.168.3.1"},
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["facts"], {
            "route_found": True, "destination": "192.168.3.0/24",
            "next_hop": "10.0.23.2", "out_interface": "GigabitEthernet0/0/1",
        })

    def test_empty_filtered_route_is_not_missing_route_evidence(self) -> None:
        result = parse_cli_output(
            "CHECK_ROUTE", read_record("route_missing/route_missing_filter_R2.txt"), device="R2",
            context={"destination": "192.168.3.1"},
        )
        self.assertFalse(result["success"])
        self.assertEqual(result["facts"], {})
        self.assertTrue(result["error"])

    def test_complete_full_route_table_proves_missing_route(self) -> None:
        result = parse_cli_output(
            "CHECK_ROUTE", read_record("route_missing/route_missing_full_R2.txt"), device="R2",
            context={"destination": "192.168.3.1"},
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["facts"], {"route_found": False})

    def test_truncated_full_table_cannot_prove_missing_route(self) -> None:
        text = read_record("route_missing/route_missing_full_R2.txt")
        text = "\n".join(line for line in text.splitlines() if "127.0.0.0/8" not in line)
        result = parse_cli_output("CHECK_ROUTE", text, device="R2", context={"destination": "192.168.3.1"})
        self.assertFalse(result["success"])
        self.assertEqual(result["facts"], {})

    def test_arp_next_hop(self) -> None:
        result = parse_cli_output(
            "CHECK_ARP", read_record("normal/normal_arp_R2.txt"), device="R2",
            context={"target_ip": "10.0.23.2"},
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["facts"], {"entry_found": True, "target_ip": "10.0.23.2"})

    def test_interface_brief_is_not_detailed_interface_output(self) -> None:
        result = parse_cli_output("CHECK_INTERFACE", read_record("normal/normal_interface_R2.txt"), device="R2")
        self.assertFalse(result["success"])
        self.assertEqual(result["facts"], {})
        self.assertTrue(result["error"])

    def test_crlf_full_table(self) -> None:
        text = read_record("route_missing/route_missing_full_R2.txt").replace("\n", "\r\n")
        result = parse_cli_output("CHECK_ROUTE", text, device="R2", context={"destination": "192.168.3.1"})
        self.assertTrue(result["success"])
        self.assertEqual(result["facts"], {"route_found": False})


if __name__ == "__main__":
    unittest.main()
