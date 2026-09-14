from __future__ import annotations

import unittest
from pathlib import Path

from parser.interface_parser import parse_interface
from parser.ping_parser import parse_ping
from parser.route_parser import parse_route
from parser.tracert_parser import parse_tracert


CASE_DIR = (
    Path(__file__).resolve().parents[1]
    / "scenarios"
    / "golden"
    / "case_001_interface_down"
)


class Case001ParserTests(unittest.TestCase):
    """Day 2 Task 3: 至少4个测试覆盖 CASE_001 的四份原始日志。

    本文件按 V1 数据契约编写（packet_loss、error 为字符串）。
    """

    def test_ping_failure(self) -> None:
        """ping 100% 丢包 → reachable=false, packet_loss=100"""
        raw = (CASE_DIR / "ping.txt").read_text(encoding="utf-8")
        result = parse_ping(raw, "R1")

        self.assertTrue(result["success"])
        self.assertEqual(result["device"], "R1")
        self.assertEqual(result["command_type"], "PING")
        self.assertFalse(result["facts"]["reachable"])
        self.assertEqual(result["facts"]["packet_loss"], 100)
        self.assertIsNone(result["error"])

    def test_tracert_interruption(self) -> None:
        """tracert 在 R2 后中断 → last_reachable_ip=10.0.12.2, suspect_device=R2"""
        raw = (CASE_DIR / "tracert.txt").read_text(encoding="utf-8")
        result = parse_tracert(
            raw, "R1", context={"ip_to_device": {"10.0.12.2": "R2"}}
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["command_type"], "TRACERT")
        self.assertEqual(result["facts"]["last_reachable_ip"], "10.0.12.2")
        self.assertEqual(result["facts"]["last_reachable_device"], "R2")
        self.assertEqual(result["facts"]["suspect_device"], "R2")
        self.assertIsNone(result["error"])

    def test_route_exists(self) -> None:
        """R2 目标路由存在 → route_found=true, out_interface=GigabitEthernet0/0/1"""
        raw = (CASE_DIR / "route_r2.txt").read_text(encoding="utf-8")
        result = parse_route(raw, "R2")

        self.assertTrue(result["success"])
        self.assertEqual(result["device"], "R2")
        self.assertEqual(result["command_type"], "DISPLAY_ROUTE")
        self.assertTrue(result["facts"]["route_found"])
        self.assertEqual(result["facts"]["out_interface"], "GigabitEthernet0/0/1")
        self.assertEqual(result["facts"]["next_hop"], "10.0.23.2")
        self.assertIsNone(result["error"])

    def test_interface_down(self) -> None:
        """R2 出接口 physical_status=DOWN → 可被准确识别"""
        raw = (CASE_DIR / "interface_r2_gigabitethernet0_0_1.txt").read_text(
            encoding="utf-8"
        )
        result = parse_interface(raw, "R2")

        self.assertTrue(result["success"])
        self.assertEqual(result["device"], "R2")
        self.assertEqual(result["command_type"], "DISPLAY_INTERFACE")
        self.assertEqual(result["facts"]["interface"], "GigabitEthernet0/0/1")
        self.assertEqual(result["facts"]["physical_status"], "DOWN")
        self.assertEqual(result["facts"]["protocol_status"], "DOWN")
        self.assertIsNone(result["error"])


if __name__ == "__main__":
    unittest.main()
