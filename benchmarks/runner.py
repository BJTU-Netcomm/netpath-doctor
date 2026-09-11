from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from agent.controller import NetPathDoctorController


DIAGNOSIS_FIELDS = (
    "diagnosis_status",
    "fault_device",
    "fault_type",
    "fault_interface",
)


@dataclass
class CaseResult:
    case_id: str
    execution_mode: str
    passed: bool
    checks: dict[str, bool]
    actual: dict[str, Any]
    expected: dict[str, Any]


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def run_case(repo_root: str | Path, case_dir: str | Path) -> CaseResult:
    repo_root = Path(repo_root)
    case_dir = Path(case_dir)
    scenario = _read_json(case_dir / "scenario.json")
    expected = _read_json(case_dir / "expected_result.json")
    return _evaluate_case(repo_root, case_dir, scenario, expected)


def _evaluate_case(
    repo_root: Path,
    case_dir: Path,
    scenario: dict[str, Any],
    expected: dict[str, Any],
) -> CaseResult:
    if scenario.get("case_id") != expected.get("case_id"):
        raise ValueError(
            f"case_id mismatch in {case_dir}: "
            f"scenario={scenario.get('case_id')!r}, expected={expected.get('case_id')!r}"
        )
    if (case_dir / "log_manifest.json").exists():
        execution_mode = "cli_replay"
    else:
        execution_mode = "mock_facts"
        mock_path = case_dir / "mock_outputs.json"
        if not mock_path.exists():
            raise FileNotFoundError(f"Case has no replay manifest or mock outputs: {case_dir}")
    actual = NetPathDoctorController(repo_root).run_scenario(case_dir / "scenario.json")

    checks = {
        field: actual.get(field) == expected.get(field)
        for field in DIAGNOSIS_FIELDS
    }
    checks["required_evidence"] = all(
        evidence in actual.get("required_evidence", [])
        for evidence in expected.get("required_evidence", [])
    )
    if "expected_actions" in expected:
        actual_actions = [step.get("action") for step in actual.get("action_trace", [])]
        checks["action_trace"] = actual_actions == expected["expected_actions"]
    if "missing_fields" in expected:
        checks["missing_fields"] = actual.get("missing_fields") == expected["missing_fields"]
    for field in ("target_network", "target_ip", "next_hop"):
        if field in expected:
            checks[field] = actual.get(field) == expected[field]
    passed = all(checks.values())
    return CaseResult(
        case_id=scenario["case_id"],
        execution_mode=execution_mode,
        passed=passed,
        checks=checks,
        actual=actual,
        expected=expected,
    )


def run_matrix_case(repo_root: str | Path, definition: dict[str, Any]) -> CaseResult:
    repo_root = Path(repo_root)
    base_dir = repo_root / "scenarios" / "golden" / definition["base_case"]
    if not base_dir.exists():
        raise FileNotFoundError(f"Matrix base case does not exist: {base_dir}")
    scenario = _read_json(base_dir / "scenario.json")
    expected = _read_json(base_dir / "expected_result.json")
    scenario.update(definition.get("scenario", {}))
    expected.update(definition.get("expected", {}))
    scenario["case_id"] = definition["case_id"]
    expected["case_id"] = definition["case_id"]
    return _evaluate_case(repo_root, base_dir, scenario, expected)


def discover_cases(repo_root: str | Path) -> list[Path]:
    root = Path(repo_root) / "scenarios" / "golden"
    if not root.exists():
        raise FileNotFoundError(f"Golden scenario directory does not exist: {root}")
    return sorted(
        case_dir
        for case_dir in root.iterdir()
        if case_dir.is_dir()
        and (case_dir / "scenario.json").exists()
        and (case_dir / "expected_result.json").exists()
    )


def run_benchmark(repo_root: str | Path) -> dict[str, Any]:
    repo_root = Path(repo_root)
    results = [run_case(repo_root, case_dir) for case_dir in discover_cases(repo_root)]
    matrix_path = repo_root / "scenarios" / "benchmark_matrix.json"
    if matrix_path.exists():
        matrix = _read_json(matrix_path)
        results.extend(run_matrix_case(repo_root, definition) for definition in matrix.get("cases", []))
    case_ids = [result.case_id for result in results]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("Golden scenarios contain duplicate case_id values")
    passed = sum(result.passed for result in results)
    mode_counts: dict[str, int] = {}
    for result in results:
        mode_counts[result.execution_mode] = mode_counts.get(result.execution_mode, 0) + 1
    return {
        "benchmark": "NetPath-Doctor golden scenarios",
        "benchmark_version": "1.0",
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "pass_rate": passed / len(results) if results else 0.0,
        "all_passed": bool(results) and passed == len(results),
        "execution_modes": mode_counts,
        "cases": [asdict(result) for result in results],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run NetPath-Doctor golden benchmarks")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="可选：将 benchmark 报告写入指定 JSON 文件",
    )
    args = parser.parse_args()
    report = run_benchmark(args.repo_root)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
