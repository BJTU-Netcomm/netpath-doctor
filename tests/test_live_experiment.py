from __future__ import annotations

import unittest

from benchmarks.live_experiment import (
    run_interface_down_benchmark,
    run_interface_down_trial,
    run_route_missing_benchmark,
    run_route_missing_trial,
)
from benchmarks.live_runner import diagnose_live_scenario


PING_UP = "5 packet(s) transmitted\n5 packet(s) received\n0.00% packet loss"
PING_DOWN = "5 packet(s) transmitted\n0 packet(s) received\n100.00% packet loss"


class FakeExperimentTransport:
    default_device = "R1"

    def __init__(self) -> None:
        self.link_up = True
        self.calls: list[tuple[str, str, object]] = []

    def send(self, device: str | None, command: str | None) -> str:
        self.calls.append(("send", str(device), command))
        if command and command.startswith("display ip routing-table"):
            return (
                "Route Flags: R - relay, D - download to fib\n"
                "Summary Count : 1\n"
                "    192.168.3.0/24  Static  60  0 RD  10.0.23.2 GigabitEthernet0/0/1"
            )
        return PING_UP if self.link_up else PING_DOWN

    def send_config(self, device: str, commands: list[str]) -> str:
        self.calls.append(("config", device, list(commands)))
        if commands[-1] == "shutdown":
            self.link_up = False
        elif commands[-1] == "undo shutdown":
            self.link_up = True
        return "commands accepted"


class FakeRouteExperimentTransport:
    default_device = "R1"

    def __init__(self) -> None:
        self.route_present = True
        self.calls: list[tuple[str, str, object]] = []

    def send(self, device: str | None, command: str | None) -> str:
        self.calls.append(("send", str(device), command))
        if command and command.startswith("display ip routing-table"):
            if device == "R1" or self.route_present:
                next_hop = "10.0.12.2" if device == "R1" else "10.0.23.2"
                interface = "GigabitEthernet0/0/0" if device == "R1" else "GigabitEthernet0/0/1"
                return (
                    "Route Flags: R - relay, D - download to fib\n"
                    "Summary Count : 1\n"
                    f"    192.168.3.0/24  Static  60  0 RD  {next_hop} {interface}"
                )
            return "Route Flags: R - relay, D - download to fib\nRoute Count : 0"
        if command and command.startswith("tracert"):
            return "traceroute to 192.168.3.1, max hops: 3\n 1  *\n 2  *\n 3  *"
        return PING_UP if self.route_present else PING_DOWN

    def send_config(self, device: str, commands: list[str]) -> str:
        self.calls.append(("config", device, list(commands)))
        if commands[-1].startswith("undo ip route-static"):
            self.route_present = False
        elif commands[-1].startswith("ip route-static"):
            self.route_present = True
        return "commands accepted"


class LiveExperimentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.scenario = {
            "case_id": "LIVE_CASE_001",
            "source_device": "R1",
            "destination_ip": "192.168.3.1",
            "destination_network": "192.168.3.0/24",
        }

    @staticmethod
    def successful_diagnosis(scenario, transport):
        if transport.link_up:
            raise AssertionError("diagnosis started before fault injection")
        return {
            "diagnosis_status": "COMPLETED",
            "fault_type": "INTERFACE_DOWN",
            "fault_device": "R2",
            "fault_interface": "GigabitEthernet0/0/1",
        }

    def test_trial_injects_diagnoses_recovers_and_verifies(self) -> None:
        transport = FakeExperimentTransport()

        result = run_interface_down_trial(
            self.scenario,
            transport,
            diagnose=self.successful_diagnosis,
            fault_device="R2",
            fault_interface="GigabitEthernet0/0/1",
        )

        self.assertTrue(result["passed"])
        self.assertTrue(transport.link_up)
        config_commands = [call[2][-1] for call in transport.calls if call[0] == "config"]
        self.assertEqual(config_commands, ["shutdown", "undo shutdown"])
        self.assertTrue(result["post_recovery"]["facts"]["reachable"])

    def test_recovery_runs_when_diagnosis_raises(self) -> None:
        transport = FakeExperimentTransport()

        def fail_diagnosis(scenario, transport):
            raise RuntimeError("diagnosis crashed")

        result = run_interface_down_trial(
            self.scenario,
            transport,
            diagnose=fail_diagnosis,
            fault_device="R2",
            fault_interface="GigabitEthernet0/0/1",
        )

        self.assertFalse(result["passed"])
        self.assertIn("diagnosis crashed", result["error"])
        self.assertTrue(result["recovery"]["success"])
        self.assertTrue(transport.link_up)

    def test_baseline_failure_does_not_inject_fault(self) -> None:
        transport = FakeExperimentTransport()
        transport.link_up = False

        result = run_interface_down_trial(
            self.scenario,
            transport,
            diagnose=self.successful_diagnosis,
            fault_device="R2",
            fault_interface="GigabitEthernet0/0/1",
        )

        self.assertFalse(result["passed"])
        self.assertIsNone(result["injection"])
        self.assertFalse(any(call[0] == "config" for call in transport.calls))

    def test_baseline_transport_error_is_reported_without_injection(self) -> None:
        transport = FakeExperimentTransport()

        def fail_send(device, command):
            raise TimeoutError("SSH timed out")

        transport.send = fail_send
        result = run_interface_down_trial(
            self.scenario,
            transport,
            diagnose=self.successful_diagnosis,
            fault_device="R2",
            fault_interface="GigabitEthernet0/0/1",
        )

        self.assertFalse(result["passed"])
        self.assertIn("SSH timed out", result["baseline"]["error"])
        self.assertFalse(any(call[0] == "config" for call in transport.calls))

    def test_benchmark_requires_every_trial_to_pass(self) -> None:
        transport = FakeExperimentTransport()
        calls = 0

        def diagnose(scenario, transport):
            nonlocal calls
            calls += 1
            result = self.successful_diagnosis(scenario, transport)
            if calls == 2:
                result["fault_type"] = "ROUTE_MISSING"
            return result

        result = run_interface_down_benchmark(
            self.scenario,
            transport,
            diagnose=diagnose,
            fault_device="R2",
            fault_interface="GigabitEthernet0/0/1",
            trials=3,
        )

        self.assertEqual(result["passed_trials"], 2)
        self.assertFalse(result["all_passed"])
        self.assertTrue(transport.link_up)

    @staticmethod
    def successful_route_diagnosis(scenario, transport):
        if transport.route_present:
            raise AssertionError("diagnosis started before route removal")
        return {
            "diagnosis_status": "COMPLETED",
            "fault_type": "ROUTE_MISSING",
            "fault_device": "R2",
            "fault_interface": None,
            "target_network": "192.168.3.0/24",
        }

    def test_route_missing_trial_removes_recovers_and_verifies(self) -> None:
        transport = FakeRouteExperimentTransport()

        result = run_route_missing_trial(
            {
                **self.scenario,
                "destination_network": "192.168.3.0/24",
            },
            transport,
            diagnose=self.successful_route_diagnosis,
            fault_device="R2",
            inject_commands=[
                "undo ip route-static 192.168.3.0 255.255.255.0 10.0.23.2"
            ],
            recovery_commands=[
                "ip route-static 192.168.3.0 255.255.255.0 10.0.23.2"
            ],
        )

        self.assertTrue(result["passed"])
        self.assertFalse(result["post_injection_route"]["facts"]["route_found"])
        self.assertTrue(result["recovery"]["success"])
        self.assertTrue(result["post_recovery"]["facts"]["reachable"])
        config_commands = [call[2][-1] for call in transport.calls if call[0] == "config"]
        self.assertEqual(
            config_commands,
            [
                "undo ip route-static 192.168.3.0 255.255.255.0 10.0.23.2",
                "ip route-static 192.168.3.0 255.255.255.0 10.0.23.2",
            ],
        )

    def test_route_missing_benchmark_requires_all_trials_to_pass(self) -> None:
        transport = FakeRouteExperimentTransport()
        calls = 0

        def diagnose(scenario, transport):
            nonlocal calls
            calls += 1
            result = self.successful_route_diagnosis(scenario, transport)
            if calls == 2:
                result["fault_type"] = "INTERFACE_DOWN"
            return result

        result = run_route_missing_benchmark(
            self.scenario,
            transport,
            diagnose=diagnose,
            fault_device="R2",
            inject_commands=["undo ip route-static 192.168.3.0 255.255.255.0 10.0.23.2"],
            recovery_commands=["ip route-static 192.168.3.0 255.255.255.0 10.0.23.2"],
            trials=3,
        )

        self.assertEqual(result["passed_trials"], 2)
        self.assertFalse(result["all_passed"])
        self.assertTrue(transport.route_present)

    def test_route_missing_trial_uses_real_diagnosis_state_machine(self) -> None:
        transport = FakeRouteExperimentTransport()
        scenario = {
            **self.scenario,
            "destination_network": "192.168.3.0/24",
            "ip_to_device": {
                "10.0.12.2": "R2",
                "10.0.23.2": "R3",
            },
        }

        result = run_route_missing_trial(
            scenario,
            transport,
            diagnose=diagnose_live_scenario,
            fault_device="R2",
            inject_commands=[
                "undo ip route-static 192.168.3.0 255.255.255.0 10.0.23.2"
            ],
            recovery_commands=[
                "ip route-static 192.168.3.0 255.255.255.0 10.0.23.2"
            ],
        )

        self.assertTrue(result["passed"])
        self.assertEqual(result["diagnosis"]["fault_type"], "ROUTE_MISSING")
        self.assertEqual(
            [step["action"] for step in result["diagnosis"]["action_trace"]],
            ["RUN_PING", "RUN_TRACERT", "CHECK_ROUTE", "CHECK_ROUTE", "FINISH_DIAGNOSIS"],
        )


if __name__ == "__main__":
    unittest.main()
