from __future__ import annotations

import unittest
from pathlib import Path

from parser.huawei_vrp import parse_cli_output


REAL_DIR = Path(__file__).resolve().parents[1] / "scenarios" / "real_outputs"


def read_real(name: str) -> str:
    return (REAL_DIR / name).read_text(encoding="utf-8")


class RealVrpOutputProbeTests(unittest.TestCase):
    """构造样例（synthetic）驱动的 VRP 格式兼容性测试。

    回显作为构造 fixture 存放于 scenarios/real_outputs/，本文件直接读取断言。
    覆盖 Route Count : 0、Administratively Down、分页、提示符、
    空 ARP 表、ping 统计段、tracert 超时行等构造 VRP 格式。
    eNSP 实测采集样例的测试见 EnspMeasuredFixtureTests。
    """

    def test_route_missing_summary_count_zero(self) -> None:
        """构造 VRP 无路由：'Summary Count : 0' → route_found=false"""
        result = parse_cli_output(
            "CHECK_ROUTE", read_real("routing-table/route_missing_routecount0.txt"), device="R2"
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["facts"], {"route_found": False})

    def test_route_missing_route_count_zero(self) -> None:
        """构造 VRP 无路由：'Route Count : 0' → route_found=false"""
        result = parse_cli_output(
            "CHECK_ROUTE", read_real("routing-table/route_missing_realcount0.txt"), device="R2"
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["facts"], {"route_found": False})

    def test_route_exists(self) -> None:
        """构造 VRP 有路由：提取 next_hop / out_interface"""
        result = parse_cli_output(
            "CHECK_ROUTE", read_real("routing-table/route_exists.txt"), device="R2"
        )
        self.assertTrue(result["success"])
        self.assertTrue(result["facts"]["route_found"])
        self.assertEqual(result["facts"]["next_hop"], "10.0.23.2")
        self.assertEqual(result["facts"]["out_interface"], "GigabitEthernet0/0/1")

    def test_route_longest_prefix_by_target(self) -> None:
        """完整路由表按目标 IP 选择最长前缀匹配"""
        result = parse_cli_output(
            "CHECK_ROUTE",
            read_real("routing-table/route_full_longest_prefix.txt"),
            device="R2",
            context={"destination": "192.168.3.1"},
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["facts"]["destination"], "192.168.3.1/32")
        self.assertEqual(result["facts"]["next_hop"], "10.0.23.3")

    def test_route_default_prefix_by_target(self) -> None:
        """目标无更长匹配时命中默认路由 0.0.0.0/0"""
        result = parse_cli_output(
            "CHECK_ROUTE",
            read_real("routing-table/route_full_longest_prefix.txt"),
            device="R2",
            context={"destination": "203.0.113.1"},
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["facts"]["destination"], "0.0.0.0/0")
        self.assertEqual(result["facts"]["next_hop"], "10.0.12.2")

    def test_route_default_only_covers_target(self) -> None:
        """仅有默认路由时仍能解析"""
        result = parse_cli_output(
            "CHECK_ROUTE",
            read_real("routing-table/route_default_only.txt"),
            device="R2",
            context={"destination": "192.168.3.10"},
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["facts"]["destination"], "0.0.0.0/0")

    def test_route_no_match_complete_table_returns_missing(self) -> None:
        """完整路由表无匹配路由 → route_found=false"""
        result = parse_cli_output(
            "CHECK_ROUTE",
            read_real("routing-table/route_no_match_complete.txt"),
            device="R2",
            context={"destination": "192.168.3.10"},
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["facts"], {"route_found": False})

    def test_route_incomplete_table_cannot_prove_missing(self) -> None:
        """不完整路由表（Routes 数不符）不能误判为缺路由，应解析失败"""
        result = parse_cli_output(
            "CHECK_ROUTE",
            read_real("routing-table/route_incomplete_mismatch.txt"),
            device="R2",
            context={"destination": "192.168.3.10"},
        )
        self.assertFalse(result["success"])
        self.assertEqual(result["facts"], {})

    def test_route_empty_output_not_missing(self) -> None:
        """空回显不应判为 route_found=false，应由传输层回退"""
        result = parse_cli_output(
            "CHECK_ROUTE", "", device="R2", context={"destination": "192.168.3.10"}
        )
        self.assertFalse(result["success"])
        self.assertEqual(result["facts"], {})

    def test_interface_administratively_down(self) -> None:
        """构造 VRP 接口被 shutdown：Administratively Down → physical_status=DOWN"""
        result = parse_cli_output(
            "CHECK_INTERFACE", read_real("interface/interface_administratively_down.txt"), device="R2"
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["facts"]["interface"], "GigabitEthernet0/0/1")
        self.assertEqual(result["facts"]["physical_status"], "DOWN")
        self.assertEqual(result["facts"]["protocol_status"], "DOWN")

    def test_interface_up(self) -> None:
        """构造 VRP 接口正常：UP/UP"""
        result = parse_cli_output(
            "CHECK_INTERFACE", read_real("interface/interface_up.txt"), device="R2"
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["facts"]["physical_status"], "UP")
        self.assertEqual(result["facts"]["protocol_status"], "UP")

    def test_arp_empty_total_zero(self) -> None:
        """构造 VRP 空 ARP 表：'Total:0' → entry_found=false"""
        result = parse_cli_output(
            "CHECK_ARP", read_real("arp/arp_empty_total0.txt"), device="R2",
            context={"target_ip": "192.168.3.10"},
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["facts"]["entry_found"], False)

    def test_arp_entry_exists(self) -> None:
        """构造 VRP 有 ARP 表项 → entry_found=true"""
        result = parse_cli_output(
            "CHECK_ARP", read_real("arp/arp_entry_exists.txt"), device="R2",
            context={"target_ip": "10.0.23.2"},
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["facts"]["entry_found"], True)
        self.assertEqual(result["facts"]["target_ip"], "10.0.23.2")

    def test_ping_100pct_loss(self) -> None:
        """构造 ping 100% 丢包 → reachable=false, packet_loss=100"""
        result = parse_cli_output(
            "RUN_PING", read_real("ping/ping_100pct_loss.txt"), device="R1"
        )
        self.assertTrue(result["success"])
        self.assertFalse(result["facts"]["reachable"])
        self.assertEqual(result["facts"]["packet_loss"], 100)

    def test_ping_ok(self) -> None:
        """构造 ping 通 → reachable=true, packet_loss=0"""
        result = parse_cli_output(
            "RUN_PING", read_real("ping/ping_ok.txt"), device="R1"
        )
        self.assertTrue(result["success"])
        self.assertTrue(result["facts"]["reachable"])
        self.assertEqual(result["facts"]["packet_loss"], 0)

    def test_tracert_interrupted(self) -> None:
        """构造 tracert 中途超时：last_reachable=R2 → suspect_device=R2"""
        result = parse_cli_output(
            "RUN_TRACERT", read_real("tracert/tracert_interrupted.txt"), device="R1",
            context={"ip_to_device": {"10.0.12.2": "R2"}},
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["facts"]["last_reachable_ip"], "10.0.12.2")
        self.assertEqual(result["facts"]["suspect_device"], "R2")


class EnspMeasuredFixtureTests(unittest.TestCase):
    """eNSP 实测采集（ensp_captured）样例测试。

    样例来自李梦瑶（feat/ensp-topology）在 eNSP 实验机上的真实抓取，
    逐份来源见 scenarios/real_outputs/SOURCES.md。命名以 `_ensp.txt` 结尾。
    """

    def test_measured_route_present_by_target_network(self) -> None:
        """实测：R2 目标路由存在，按目标网段查询命中 /24"""
        result = parse_cli_output(
            "CHECK_ROUTE",
            read_real("routing-table/route_r2_route_present_ensp.txt"),
            device="R2",
            context={"destination": "192.168.3.0"},
        )
        self.assertTrue(result["success"])
        self.assertTrue(result["facts"]["route_found"])
        self.assertEqual(result["facts"]["destination"], "192.168.3.0/24")
        self.assertEqual(result["facts"]["next_hop"], "10.0.23.2")
        self.assertEqual(result["facts"]["out_interface"], "GigabitEthernet0/0/1")

    def test_measured_route_present_covers_host_target(self) -> None:
        """实测：目标主机 IP 落在已存在网段内 → 命中该路由"""
        result = parse_cli_output(
            "CHECK_ROUTE",
            read_real("routing-table/route_r2_route_present_ensp.txt"),
            device="R2",
            context={"destination": "192.168.3.10"},
        )
        self.assertTrue(result["success"])
        self.assertTrue(result["facts"]["route_found"])
        self.assertEqual(result["facts"]["destination"], "192.168.3.0/24")

    def test_measured_empty_body_is_not_route_missing(self) -> None:
        """实测：过滤查询空正文（仅命令回显与提示符）→ 解析失败，绝不判 route_found=false"""
        result = parse_cli_output(
            "CHECK_ROUTE",
            read_real("routing-table/route_r2_empty_body_ensp.txt"),
            device="R2",
            context={"destination": "192.168.3.0"},
        )
        self.assertFalse(result["success"])
        self.assertEqual(result["facts"], {})
        self.assertNotIn("route_found", result["facts"])
        self.assertTrue(result["error"])


if __name__ == "__main__":
    unittest.main()