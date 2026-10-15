"""Offline benchmark for the AI tool/harness contract.

This benchmark uses a deterministic scripted planner, not Qwen, so its score is
repeatable and does not pretend to measure model intelligence.  It verifies
that each golden case can pass through the same read-only tool protocol,
ReplayExecutor, provenance envelope, and diagnosis validation used by the
real Bailian client.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from agent.command_mapper import load_action_catalog
from ai.harness import AIHarness
from tool_server.replay_executor import ReplayExecutor

ROOT = Path(__file__).resolve().parents[1]


class ScriptedClient:
    """A deterministic stand-in for a provider response stream."""

    def __init__(self, responses: list[dict[str, Any]]):
        self.responses = iter(responses)

    def chat(self, messages, *, tools=None, **kwargs):
        return next(self.responses)


def _call(name: str, arguments: dict[str, Any], number: int) -> dict[str, Any]:
    return {
        "choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [{
            "id": f"benchmark-call-{number}",
            "type": "function",
            "function": {"name": name, "arguments": json.dumps(arguments, ensure_ascii=False)},
        }]}}]
    }


def _finish(diagnosis: dict[str, Any], number: int) -> dict[str, Any]:
    return _call("finish_diagnosis", {"diagnosis": diagnosis}, number)


def _request_more(number: int) -> dict[str, Any]:
    return _call("request_more_data", {"missing_fields": ["deeper_control_plane_checks"]}, number)


def _plan(scenario: dict[str, Any], expected: dict[str, Any]) -> list[dict[str, Any]]:
    destination = scenario["destination_ip"]
    action_calls: list[tuple[str, dict[str, Any]]] = [
        ("run_ping", {"device": "R1", "target_ip": destination}),
    ]
    fault_type = expected.get("fault_type")
    if expected.get("diagnosis_status") != "NORMAL":
        action_calls.append(("run_tracert", {"device": "R1", "target_ip": destination}))
        action_calls.append(("check_route", {"device": "R2", "destination": destination}))
    if fault_type in {"INTERFACE_DOWN", "ARP_UNRESOLVED", "NEXT_HOP_UNREACHABLE"}:
        action_calls.append(("check_interface", {"device": "R2", "interface": "GigabitEthernet0/0/1"}))
    if fault_type in {"ARP_UNRESOLVED", "NEXT_HOP_UNREACHABLE"}:
        arp_target = "10.0.23.2" if fault_type == "NEXT_HOP_UNREACHABLE" else destination
        action_calls.append(("check_arp", {"device": "R2", "target_ip": arp_target}))
    responses = [_call(name, args, index) for index, (name, args) in enumerate(action_calls, start=1)]
    if expected.get("diagnosis_status") == "NEED_MORE_DATA":
        responses.append(_request_more(len(responses) + 1))
        return responses
    diagnosis = {
        "diagnosis_status": expected["diagnosis_status"],
        "fault_type": expected.get("fault_type"),
        "fault_device": expected.get("fault_device"),
        "fault_interface": expected.get("fault_interface"),
        "evidence": ["scripted protocol benchmark evidence"],
    }
    for field in ("target_network", "target_ip", "next_hop"):
        if field in expected:
            diagnosis[field] = expected[field]
    responses.append(_finish(diagnosis, len(responses) + 1))
    return responses


@dataclass
class AIContractCase:
    case_id: str
    passed: bool
    checks: dict[str, bool]
    diagnosis: dict[str, Any]
    successful_observations: int
    replay_refs: int
    tool_calls: int


def run_case(case_dir: Path, catalog: dict[str, Any], scenario: dict[str, Any] | None = None, expected: dict[str, Any] | None = None) -> AIContractCase:
    scenario = scenario or json.loads((case_dir / "scenario.json").read_text(encoding="utf-8"))
    expected = expected or json.loads((case_dir / "expected_result.json").read_text(encoding="utf-8"))
    executor = ReplayExecutor(scenario, catalog, case_dir)
    result = AIHarness(ScriptedClient(_plan(scenario, expected)), executor, catalog).diagnose(scenario)
    diagnosis = result.get("diagnosis", {})
    trace = result.get("tool_trace", [])
    checks = {
        "diagnosis_status": diagnosis.get("diagnosis_status") == expected.get("diagnosis_status"),
        "fault_type": diagnosis.get("fault_type") == expected.get("fault_type"),
        "fault_device": diagnosis.get("fault_device") == expected.get("fault_device"),
        "fault_interface": diagnosis.get("fault_interface") == expected.get("fault_interface"),
        "terminal_action": bool(trace) and trace[-1].get("action") in {"FINISH_DIAGNOSIS", "REQUEST_MORE_DATA"},
        "no_write_tool": all(step.get("tool") not in {"run_shell", "shutdown", "apply_config"} for step in trace),
        "replay_provenance": all(
            step.get("result", {}).get("raw_ref", "").startswith("replay://")
            for step in trace
            if step.get("action") in {"RUN_PING", "RUN_TRACERT", "CHECK_ROUTE", "CHECK_INTERFACE", "CHECK_ARP"}
            and step.get("result", {}).get("success")
        ),
    }
    for field in ("target_network", "target_ip", "next_hop"):
        if field in expected:
            checks[field] = diagnosis.get(field) == expected[field]
    successful = [step for step in trace if step.get("action") in {"RUN_PING", "RUN_TRACERT", "CHECK_ROUTE", "CHECK_INTERFACE", "CHECK_ARP"} and step.get("result", {}).get("success")]
    refs = [step for step in successful if step.get("result", {}).get("raw_ref")]
    return AIContractCase(scenario["case_id"], all(checks.values()), checks, diagnosis, len(successful), len(refs), len(trace))


def run_benchmark(repo_root: str | Path = ROOT) -> dict[str, Any]:
    repo_root = Path(repo_root)
    catalog = load_action_catalog(repo_root / "rules" / "action_catalog.json")
    case_dirs = sorted((repo_root / "scenarios" / "golden").glob("case_*/"))
    cases = [run_case(case_dir, catalog) for case_dir in case_dirs]
    matrix_path = repo_root / "scenarios" / "benchmark_matrix.json"
    if matrix_path.exists():
        matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
        for definition in matrix.get("cases", []):
            base_dir = repo_root / "scenarios" / "golden" / definition["base_case"]
            scenario = json.loads((base_dir / "scenario.json").read_text(encoding="utf-8"))
            expected = json.loads((base_dir / "expected_result.json").read_text(encoding="utf-8"))
            scenario.update(definition.get("scenario", {}))
            expected.update(definition.get("expected", {}))
            scenario["case_id"] = definition["case_id"]
            expected["case_id"] = definition["case_id"]
            cases.append(run_case(base_dir, catalog, scenario, expected))
    passed = sum(case.passed for case in cases)
    return {
        "benchmark": "NetPath-Doctor AI tool contract benchmark",
        "benchmark_version": "1.0",
        "executor": "ReplayExecutor",
        "planner": "deterministic_scripted_planner",
        "model_accuracy_claim": False,
        "total": len(cases),
        "passed": passed,
        "failed": len(cases) - passed,
        "pass_rate": passed / len(cases) if cases else 0.0,
        "all_passed": bool(cases) and passed == len(cases),
        "cases": [asdict(case) for case in cases],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the offline AI tool contract benchmark")
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = run_benchmark(args.repo_root)
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
