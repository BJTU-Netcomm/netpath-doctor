from __future__ import annotations

import unittest
from pathlib import Path

from agent.action_schema import AgentAction, validate_action
from agent.command_mapper import load_action_catalog, render_command
from agent.state_machine import DiagnosisStateMachine
from tool_server.mock_executor import MockExecutor
from tool_server.live_executor import LiveExecutor


REPO_ROOT = Path(__file__).resolve().parents[1]


class CommandMapperTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = load_action_catalog(REPO_ROOT / "rules" / "action_catalog.json")

    def test_render_huawei_route_command(self) -> None:
        action = AgentAction(
            action="CHECK_ROUTE",
            target_device="R2",
            parameters={"destination": "192.168.3.10"},
            reason="测试命令映射",
        )
        self.assertEqual(render_command(action, self.catalog), "display ip routing-table 192.168.3.10")

    def test_validate_missing_interface(self) -> None:
        action = AgentAction(action="CHECK_INTERFACE", target_device="R2", parameters={})
        with self.assertRaises(ValueError):
            validate_action(action, self.catalog)


class MvpFlowTests(unittest.TestCase):
    def test_case_001_finishes_with_interface_down(self) -> None:
        scenario = {
            "case_id": "CASE_001",
            "destination_ip": "192.168.3.10",
            "vendor": "huawei_vrp",
            "ground_truth": {
                "fault_device": "R2",
                "fault_interface": "GigabitEthernet0/0/1",
            },
            "mock_outputs": {
                "RUN_PING": {"reachable": False, "packet_loss": 100},
                "RUN_TRACERT": {"last_reachable_device": "R2", "suspect_device": "R2"},
                "CHECK_ROUTE": {"R2": {"route_found": True, "out_interface": "GigabitEthernet0/0/1"}},
                "CHECK_INTERFACE": {
                    "R2:GigabitEthernet0/0/1": {
                        "interface": "GigabitEthernet0/0/1",
                        "physical_status": "DOWN",
                        "protocol_status": "DOWN",
                    }
                },
            },
        }
        catalog = load_action_catalog(REPO_ROOT / "rules" / "action_catalog.json")
        result = DiagnosisStateMachine().run(scenario, MockExecutor(scenario, catalog))

        self.assertEqual(result["diagnosis_status"], "COMPLETED")
        self.assertEqual(result["fault_device"], "R2")
        self.assertEqual(result["fault_type"], "INTERFACE_DOWN")
        self.assertEqual(result["fault_interface"], "GigabitEthernet0/0/1")
        self.assertEqual(
            [step["action"] for step in result["action_trace"]],
            ["RUN_PING", "RUN_TRACERT", "CHECK_ROUTE", "CHECK_INTERFACE", "FINISH_DIAGNOSIS"],
        )

    def test_executor_failure_requests_more_data(self) -> None:
        class FailedExecutor:
            def execute(self, action: AgentAction) -> dict:
                return {"success": False, "facts": {}, "error": "parse failed"}

        scenario = {"case_id": "CASE_ERROR", "destination_ip": "192.168.3.10"}
        result = DiagnosisStateMachine().run(scenario, FailedExecutor())

        self.assertEqual(result["diagnosis_status"], "NEED_MORE_DATA")
        self.assertEqual(result["missing_fields"], ["ping_facts"])
        self.assertEqual(
            [step["action"] for step in result["action_trace"]],
            ["RUN_PING", "REQUEST_MORE_DATA"],
        )

    def test_live_executor_sends_command_and_parses_reply(self) -> None:
        catalog = load_action_catalog(REPO_ROOT / "rules" / "action_catalog.json")

        class FakeTransport:
            def __init__(self) -> None:
                self.calls = []

            def send(self, device: str | None, command: str | None) -> str:
                self.calls.append((device, command))
                return "5 packet(s) transmitted\n5 packet(s) received\n0.00% packet loss"

        transport = FakeTransport()
        executor = LiveExecutor({"vendor": "huawei_vrp"}, catalog, transport)
        result = executor.execute(
            AgentAction(action="RUN_PING", parameters={"target_ip": "192.168.3.10"})
        )

        self.assertTrue(result["success"])
        self.assertTrue(result["facts"]["reachable"])
        self.assertEqual(transport.calls, [(None, "ping 192.168.3.10")])


if __name__ == "__main__":
    unittest.main()
