"""Synthetic regressions for route withdrawal, never presented as live evidence."""
import unittest

from agent.state_machine import DiagnosisStateMachine
from benchmarks.live_experiment import run_interface_down_trial
from benchmarks.live_runner import diagnose_live_scenario


class WithdrawalExecutor:
    def __init__(self, interface_result):
        self.interface_result = interface_result

    def execute(self, action):
        facts = {
            "RUN_PING": {"reachable": False, "packet_loss": 100},
            "RUN_TRACERT": {"suspect_device": "R2", "last_reachable_device": "R2"},
            "CHECK_ROUTE": {"route_found": False},
        }
        if action.action == "CHECK_INTERFACE":
            return self.interface_result
        return {"success": True, "facts": facts[action.action]}


class RouteWithdrawalTests(unittest.TestCase):
    def run_case(self, interface_result, baseline=True):
        scenario = {"case_id": "REGRESSION", "destination_ip": "192.168.3.1",
                    "destination_network": "192.168.3.0/24"}
        if baseline:
            scenario["baseline_route_facts"] = {"R2": {
                "route_found": True, "out_interface": "GigabitEthernet0/0/1",
                "next_hop": "10.0.23.2",
            }}
        return DiagnosisStateMachine().run(scenario, WithdrawalExecutor(interface_result))

    def test_withdrawn_route_and_down_interface_identify_link_fault(self):
        result = self.run_case({"success": True, "facts": {
            "physical_status": "DOWN", "protocol_status": "DOWN"}})
        self.assertEqual(result["fault_type"], "INTERFACE_DOWN")
        self.assertEqual(result["fault_interface"], "GigabitEthernet0/0/1")
        self.assertIn("R2 目标路由不存在", result["required_evidence"])
        self.assertTrue(any("physical_status 为 DOWN" in e for e in result["required_evidence"]))

    def test_missing_route_and_healthy_interface_identify_route_fault(self):
        result = self.run_case({"success": True, "facts": {
            "physical_status": "UP", "protocol_status": "UP"}})
        self.assertEqual(result["fault_type"], "ROUTE_MISSING")
        self.assertEqual(result["target_network"], "192.168.3.0/24")

    def test_unreadable_interface_does_not_guess_route_fault(self):
        result = self.run_case({"success": False, "facts": {}, "error": "EMPTY_OUTPUT"})
        self.assertEqual(result["diagnosis_status"], "NEED_MORE_DATA")
        self.assertIsNone(result["fault_type"])

    def test_protocol_down_needs_more_data(self):
        result = self.run_case({"success": True, "facts": {
            "physical_status": "UP", "protocol_status": "DOWN"}})
        self.assertEqual(result["diagnosis_status"], "NEED_MORE_DATA")
        self.assertEqual(result["missing_fields"], ["interface_link_state"])

    def test_without_baseline_preserves_replay_route_missing_path(self):
        result = self.run_case(None, baseline=False)
        self.assertEqual(result["fault_type"], "ROUTE_MISSING")
        self.assertNotIn("CHECK_INTERFACE", [a["action"] for a in result["action_trace"]])

    def test_live_pipeline_handles_shutdown_with_route_withdrawal(self):
        class Transport:
            default_device = "R1"
            up = True

            def send(self, device, command):
                if command.startswith("ping"):
                    return "5 packet(s) transmitted\n" + (
                        "5 packet(s) received\n0.00% packet loss" if self.up else
                        "0 packet(s) received\n100.00% packet loss")
                if command.startswith("tracert"):
                    return "1  10.0.12.2  5 ms\n2  * * *"
                if command.startswith("display ip routing-table"):
                    header = "Route Flags: R - relay, D - download to fib\n"
                    return header + ("Route Count : 1\n192.168.3.0/24 Static 60 0 RD 10.0.23.2 GigabitEthernet0/0/1"
                                     if self.up else "Route Count : 0")
                if command.startswith("display interface"):
                    state = "UP" if self.up else "Administratively DOWN"
                    protocol = "UP" if self.up else "DOWN"
                    return f"GigabitEthernet0/0/1 current state : {state}\nLine protocol current state : {protocol}"
                raise AssertionError(command)

            def send_config(self, device, commands):
                self.up = commands[-1] == "undo shutdown"
                return "commands accepted"

        transport = Transport()
        result = run_interface_down_trial(
            {"case_id": "REGRESSION", "source_device": "R1", "destination_ip": "192.168.3.1",
             "ip_to_device": {"10.0.12.2": "R2"}}, transport,
            diagnose=diagnose_live_scenario, fault_device="R2",
            fault_interface="GigabitEthernet0/0/1")
        self.assertTrue(result["passed"])
        self.assertEqual(result["diagnosis"]["fault_type"], "INTERFACE_DOWN")
        self.assertTrue(transport.up)
