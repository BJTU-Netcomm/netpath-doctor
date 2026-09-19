from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Callable, Protocol

from benchmarks.live_runner import diagnose_live_scenario
from parser.huawei_vrp import parse_cli_output
from tool_server.ssh_transport import SSHTransport


REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_ERROR_PATTERN = re.compile(r"(?im)^\s*(?:error:|%)")


class ExperimentTransport(Protocol):
    default_device: str

    def send(self, device: str | None, command: str | None) -> str:
        ...

    def send_config(self, device: str, commands: list[str]) -> str:
        ...


def _ping(transport: ExperimentTransport, device: str, target_ip: str) -> dict[str, Any]:
    raw_output = transport.send(device, f"ping {target_ip}")
    return parse_cli_output("PING", raw_output, device=device)


def _apply_interface_state(
    transport: ExperimentTransport,
    device: str,
    interface: str,
    command: str,
) -> dict[str, Any]:
    commands = [f"interface {interface}", command]
    output = transport.send_config(device, commands)
    error_match = CONFIG_ERROR_PATTERN.search(output)
    return {
        "device": device,
        "interface": interface,
        "commands": commands,
        "success": error_match is None,
        "error": error_match.group(0).strip() if error_match else None,
    }


def run_interface_down_trial(
    scenario: dict[str, Any],
    transport: ExperimentTransport,
    *,
    diagnose: Callable[[dict[str, Any], ExperimentTransport], dict[str, Any]],
    fault_device: str,
    fault_interface: str,
) -> dict[str, Any]:
    source_device = str(scenario.get("source_device") or transport.default_device)
    target_ip = str(scenario["destination_ip"])
    report: dict[str, Any] = {
        "case_id": scenario["case_id"],
        "fault_device": fault_device,
        "fault_interface": fault_interface,
        "baseline": None,
        "injection": None,
        "diagnosis": None,
        "recovery": None,
        "post_recovery": None,
        "passed": False,
    }

    try:
        baseline = _ping(transport, source_device, target_ip)
    except Exception as exc:
        report["baseline"] = {
            "success": False,
            "facts": {},
            "error": f"{type(exc).__name__}: {exc}",
        }
        report["error"] = "Baseline connectivity check could not run"
        return report
    report["baseline"] = baseline
    if not baseline.get("success") or not baseline.get("facts", {}).get("reachable"):
        report["error"] = "Baseline connectivity failed; fault was not injected"
        return report

    try:
        injection = _apply_interface_state(
            transport, fault_device, fault_interface, "shutdown"
        )
        report["injection"] = injection
        if not injection["success"]:
            report["error"] = "VRP rejected the fault injection command"
            return report
        report["diagnosis"] = diagnose(scenario, transport)
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        try:
            report["recovery"] = _apply_interface_state(
                transport, fault_device, fault_interface, "undo shutdown"
            )
        except Exception as exc:
            report["recovery"] = {
                "success": False,
                "error": f"{type(exc).__name__}: {exc}",
            }

    try:
        report["post_recovery"] = _ping(transport, source_device, target_ip)
    except Exception as exc:
        report["post_recovery"] = {
            "success": False,
            "facts": {},
            "error": f"{type(exc).__name__}: {exc}",
        }

    diagnosis = report.get("diagnosis") or {}
    post_recovery = report.get("post_recovery") or {}
    report["passed"] = all(
        (
            diagnosis.get("diagnosis_status") == "COMPLETED",
            diagnosis.get("fault_type") == "INTERFACE_DOWN",
            diagnosis.get("fault_device") == fault_device,
            diagnosis.get("fault_interface") == fault_interface,
            bool((report.get("recovery") or {}).get("success")),
            bool(post_recovery.get("success")),
            bool(post_recovery.get("facts", {}).get("reachable")),
        )
    )
    return report


def run_interface_down_benchmark(
    scenario: dict[str, Any],
    transport: ExperimentTransport,
    *,
    diagnose: Callable[[dict[str, Any], ExperimentTransport], dict[str, Any]],
    fault_device: str,
    fault_interface: str,
    trials: int = 3,
) -> dict[str, Any]:
    if trials < 1:
        raise ValueError("trials must be at least 1")
    trial_results = [
        run_interface_down_trial(
            scenario,
            transport,
            diagnose=diagnose,
            fault_device=fault_device,
            fault_interface=fault_interface,
        )
        for _ in range(trials)
    ]
    passed_trials = sum(bool(trial["passed"]) for trial in trial_results)
    return {
        "benchmark": "eNSP INTERFACE_DOWN live benchmark",
        "case_id": scenario["case_id"],
        "requested_trials": trials,
        "passed_trials": passed_trials,
        "all_passed": passed_trials == trials,
        "trials": trial_results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the live eNSP INTERFACE_DOWN benchmark with guaranteed recovery"
    )
    parser.add_argument("scenario", type=Path, help="Live scenario JSON path")
    parser.add_argument(
        "--devices",
        type=Path,
        default=REPO_ROOT / "config" / "devices.local.json",
        help="Local SSH device inventory",
    )
    parser.add_argument("--fault-device")
    parser.add_argument("--fault-interface")
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "reports" / "live" / "experiment_latest.json",
    )
    parser.add_argument(
        "--raw-output-dir",
        type=Path,
        default=REPO_ROOT / "reports" / "live" / "experiment_raw",
    )
    args = parser.parse_args()

    scenario = json.loads(args.scenario.read_text(encoding="utf-8"))
    experiment_control = scenario.get("experiment_control", {})
    fault_device = args.fault_device or experiment_control.get("fault_device")
    fault_interface = args.fault_interface or experiment_control.get("fault_interface")
    if not fault_device or not fault_interface:
        parser.error(
            "fault device and interface are required in the scenario or command line"
        )
    transport = SSHTransport.from_json(
        args.devices,
        capture_dir=args.raw_output_dir,
    )
    result = run_interface_down_benchmark(
        scenario,
        transport,
        diagnose=diagnose_live_scenario,
        fault_device=fault_device,
        fault_interface=fault_interface,
        trials=args.trials,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
