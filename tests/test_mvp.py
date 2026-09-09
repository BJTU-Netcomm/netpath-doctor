from __future__ import annotations

import unittest
from pathlib import Path

from agent.action_schema import AgentAction, validate_action
from agent.command_mapper import load_action_catalog, render_command
from agent.state_machine import DiagnosisStateMachine
from tool_server.mock_executor import MockExecutor


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


if __name__ == "__main__":
    unittest.main()
