from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from typing import Any, Callable, Protocol

from benchmarks.live_runner import diagnose_live_scenario
from parser.huawei_vrp import parse_cli_output
from tool_server.ensp_console_transport import ENSPConsoleTransport
from tool_server.ssh_transport import SSHTransport


REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_ERROR_PATTERN = re.compile(r"(?im)^\s*(?:error:|%)")


class ExperimentTransport(Protocol):
    default_device: str

    def send(self, device: str | None, command: str | None) -> str:
        ...

    def send_config(self, device: str, commands: list[str]) -> str:
        ...


def _recover_interface(
    transport: ExperimentTransport,
    device: str,
    interface: str,
) -> dict[str, Any]:
    """Recover a live interface and use transport-specific verification when available."""
    recover = getattr(transport, "recover_interface", None)
    if callable(recover):
        return recover(device, interface)
    return _apply_interface_state(transport, device, interface, "undo shutdown")


def _ping(transport: ExperimentTransport, device: str, target_ip: str) -> dict[str, Any]:
    raw_output = transport.send(device, f"ping {target_ip}")
    return parse_cli_output("PING", raw_output, device=device)


def _route(transport: ExperimentTransport, device: str, target_ip: str) -> dict[str, Any]:
    raw_output = transport.send(device, f"display ip routing-table {target_ip}")
    return parse_cli_output(
        "CHECK_ROUTE",
        raw_output,
        device=device,
        context={"destination": target_ip},
    )


def _apply_interface_state(
    transport: ExperimentTransport,
    device: str,
    interface: str,
    command: str,
) -> dict[str, Any]:
    result = _apply_config_commands(
        transport,
        device,
        [f"interface {interface}", command],
    )
    result["interface"] = interface
    return result


def _apply_config_commands(
    transport: ExperimentTransport,
    device: str,
    commands: list[str],
) -> dict[str, Any]:
    output = transport.send_config(device, commands)
    error_match = CONFIG_ERROR_PATTERN.search(output)
    return {
        "device": device,
        "interface": None,
        "commands": commands,
        "success": error_match is None,
        "error": error_match.group(0).strip() if error_match else None,
    }


def _recover_route(
    transport: ExperimentTransport,
    device: str,
    target_ip: str,
    commands: list[str],
    *,
    attempts: int = 3,
    settle_seconds: float = 0.5,
) -> dict[str, Any]:
    """Restore a route and verify that VRP exposes it again."""
    if attempts < 1:
        raise ValueError("attempts must be at least 1")
    errors: list[str] = []
    for attempt in range(1, attempts + 1):
        try:
            applied = _apply_config_commands(transport, device, commands)
        except Exception as exc:
            errors.append(f"attempt {attempt}: {type(exc).__name__}: {exc}")
            continue
        if settle_seconds:
            time.sleep(settle_seconds)
        try:
            verification = _route(transport, device, target_ip)
        except Exception as exc:
            errors.append(f"attempt {attempt}: route verification failed: {type(exc).__name__}: {exc}")
            continue
        if verification.get("success") and verification.get("facts", {}).get("route_found"):
            return {
                "device": device,
                "commands": commands,
                "success": True,
                "attempts": attempt,
                "verification": verification,
                "error": None,
            }
        if not applied["success"]:
            errors.append(f"attempt {attempt}: {applied.get('error', 'command rejected')}")
        errors.append(
            f"attempt {attempt}: route verification failed: "
            f"{verification.get('error', 'route not found')}"
        )
    return {
        "device": device,
        "commands": commands,
        "success": False,
        "attempts": attempts,
        "verification": None,
        "error": "; ".join(errors) or "route recovery failed",
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
        "pre_injection_route": None,
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
        pre_injection_route = _route(transport, fault_device, target_ip)
    except Exception as exc:
        report["pre_injection_route"] = {
            "success": False,
            "facts": {},
            "error": f"{type(exc).__name__}: {exc}",
        }
        report["error"] = "Pre-injection route snapshot could not run; fault was not injected"
        return report
    report["pre_injection_route"] = pre_injection_route
    if not pre_injection_route.get("success") or not pre_injection_route.get("facts", {}).get(
        "route_found"
    ):
        report["error"] = "Pre-injection route snapshot failed; fault was not injected"
        return report

    try:
        injection = _apply_interface_state(
            transport, fault_device, fault_interface, "shutdown"
        )
        report["injection"] = injection
        if not injection["success"]:
            report["error"] = "VRP rejected the fault injection command"
            return report
        diagnosis_scenario = dict(scenario)
        diagnosis_scenario["baseline_route_facts"] = {
            fault_device: dict(pre_injection_route["facts"])
        }
        report["diagnosis"] = diagnose(diagnosis_scenario, transport)
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        try:
            report["recovery"] = _recover_interface(
                transport, fault_device, fault_interface
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


def run_route_missing_trial(
    scenario: dict[str, Any],
    transport: ExperimentTransport,
    *,
    diagnose: Callable[[dict[str, Any], ExperimentTransport], dict[str, Any]],
    fault_device: str,
    inject_commands: list[str],
    recovery_commands: list[str],
) -> dict[str, Any]:
    """Remove a static route, diagnose it, then restore and verify it."""
    source_device = str(scenario.get("source_device") or transport.default_device)
    target_ip = str(scenario["destination_ip"])
    report: dict[str, Any] = {
        "case_id": scenario["case_id"],
        "fault_device": fault_device,
        "fault_type": "ROUTE_MISSING",
        "fault_interface": None,
        "baseline": None,
        "pre_injection_route": None,
        "injection": None,
        "post_injection_route": None,
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
        report["error"] = "Baseline connectivity failed; route was not removed"
        return report

    try:
        pre_injection_route = _route(transport, fault_device, target_ip)
    except Exception as exc:
        report["pre_injection_route"] = {
            "success": False,
            "facts": {},
            "error": f"{type(exc).__name__}: {exc}",
        }
        report["error"] = "Pre-injection route snapshot could not run; route was not removed"
        return report
    report["pre_injection_route"] = pre_injection_route
    if not pre_injection_route.get("success") or not pre_injection_route.get("facts", {}).get(
        "route_found"
    ):
        report["error"] = "Pre-injection route snapshot failed; route was not removed"
        return report

    injection_started = False
    try:
        injection_started = True
        injection = _apply_config_commands(transport, fault_device, inject_commands)
        report["injection"] = injection
        if not injection["success"]:
            report["error"] = "VRP rejected the route removal command"
            return report

        post_injection_route = _route(transport, fault_device, target_ip)
        report["post_injection_route"] = post_injection_route
        if (
            not post_injection_route.get("success")
            or post_injection_route.get("facts", {}).get("route_found")
        ):
            report["error"] = (
                "Route removal could not be verified"
                if not post_injection_route.get("success")
                else "Route still exists after removal command"
            )
            return report

        report["diagnosis"] = diagnose(dict(scenario), transport)
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if injection_started:
            try:
                report["recovery"] = _recover_route(
                    transport,
                    fault_device,
                    target_ip,
                    recovery_commands,
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
    recovery = report.get("recovery") or {}
    report["passed"] = all(
        (
            diagnosis.get("diagnosis_status") == "COMPLETED",
            diagnosis.get("fault_type") == "ROUTE_MISSING",
            diagnosis.get("fault_device") == fault_device,
            diagnosis.get("fault_interface") is None,
            diagnosis.get("target_network")
            == scenario.get("destination_network", scenario["destination_ip"]),
            bool(recovery.get("success")),
            bool(post_recovery.get("success")),
            bool(post_recovery.get("facts", {}).get("reachable")),
        )
    )
    return report


def run_route_missing_benchmark(
    scenario: dict[str, Any],
    transport: ExperimentTransport,
    *,
    diagnose: Callable[[dict[str, Any], ExperimentTransport], dict[str, Any]],
    fault_device: str,
    inject_commands: list[str],
    recovery_commands: list[str],
    trials: int = 3,
) -> dict[str, Any]:
    if trials < 1:
        raise ValueError("trials must be at least 1")
    trial_results = [
        run_route_missing_trial(
            scenario,
            transport,
            diagnose=diagnose,
            fault_device=fault_device,
            inject_commands=inject_commands,
            recovery_commands=recovery_commands,
        )
        for _ in range(trials)
    ]
    passed_trials = sum(bool(trial["passed"]) for trial in trial_results)
    return {
        "benchmark": "eNSP ROUTE_MISSING live benchmark",
        "case_id": scenario["case_id"],
        "requested_trials": trials,
        "passed_trials": passed_trials,
        "all_passed": passed_trials == trials,
        "trials": trial_results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a live eNSP fault benchmark with guaranteed recovery"
    )
    parser.add_argument("scenario", type=Path, help="Live scenario JSON path")
    parser.add_argument(
        "--devices",
        type=Path,
        default=REPO_ROOT / "config" / "devices.local.json",
        help="Local device inventory",
    )
    parser.add_argument(
        "--transport",
        choices=("ssh", "ensp-console"),
        default="ssh",
        help="CLI transport used to reach the running devices",
    )
    parser.add_argument("--fault-device")
    parser.add_argument("--fault-interface")
    parser.add_argument(
        "--fault-type",
        choices=("INTERFACE_DOWN", "ROUTE_MISSING"),
        help="Fault experiment selected when the scenario does not define one",
    )
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
    fault_type = args.fault_type or experiment_control.get("fault_type") or "INTERFACE_DOWN"
    fault_device = args.fault_device or experiment_control.get("fault_device")
    if not fault_device:
        parser.error("fault device is required in the scenario or command line")
    transport_class = {
        "ssh": SSHTransport,
        "ensp-console": ENSPConsoleTransport,
    }[args.transport]
    transport = transport_class.from_json(
        args.devices,
        capture_dir=args.raw_output_dir,
    )
    if fault_type == "INTERFACE_DOWN":
        fault_interface = args.fault_interface or experiment_control.get("fault_interface")
        if not fault_interface:
            parser.error(
                "fault interface is required for INTERFACE_DOWN in the scenario or command line"
            )
        result = run_interface_down_benchmark(
            scenario,
            transport,
            diagnose=diagnose_live_scenario,
            fault_device=fault_device,
            fault_interface=fault_interface,
            trials=args.trials,
        )
    else:
        inject_commands = experiment_control.get("inject_commands")
        recovery_commands = experiment_control.get("recovery_commands")
        if not isinstance(inject_commands, list) or not isinstance(recovery_commands, list):
            parser.error(
                "ROUTE_MISSING requires inject_commands and recovery_commands in experiment_control"
            )
        result = run_route_missing_benchmark(
            scenario,
            transport,
            diagnose=diagnose_live_scenario,
            fault_device=fault_device,
            inject_commands=[str(command) for command in inject_commands],
            recovery_commands=[str(command) for command in recovery_commands],
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
