"""Run Qwen/百炼 over the 20 Replay cases and produce an honest report."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from agent.command_mapper import load_action_catalog
from ai.bailian_client import BailianClient
from ai.harness import AIHarness
from tool_server.replay_executor import ReplayExecutor

ROOT = Path(__file__).resolve().parents[1]


def _cases(root: Path):
    for case_dir in sorted((root / "scenarios" / "golden").glob("case_*/")):
        yield case_dir, json.loads((case_dir / "scenario.json").read_text(encoding="utf-8")), json.loads((case_dir / "expected_result.json").read_text(encoding="utf-8"))
    matrix = root / "scenarios" / "benchmark_matrix.json"
    if matrix.exists():
        for definition in json.loads(matrix.read_text(encoding="utf-8")).get("cases", []):
            case_dir = root / "scenarios" / "golden" / definition["base_case"]
            scenario = json.loads((case_dir / "scenario.json").read_text(encoding="utf-8"))
            expected = json.loads((case_dir / "expected_result.json").read_text(encoding="utf-8"))
            scenario.update(definition.get("scenario", {})); expected.update(definition.get("expected", {}))
            scenario["case_id"] = definition["case_id"]; expected["case_id"] = definition["case_id"]
            yield case_dir, scenario, expected


def run(root: Path, *, max_turns: int = 8, max_tokens: int = 768) -> dict[str, Any]:
    catalog = load_action_catalog(root / "rules" / "action_catalog.json")
    client = BailianClient()
    rows = []
    for case_dir, scenario, expected in _cases(root):
        started = time.perf_counter()
        executor = ReplayExecutor(scenario, catalog, case_dir)
        result = AIHarness(client, executor, catalog, max_turns=max_turns, max_tokens=max_tokens).diagnose(scenario)
        diagnosis = result.get("diagnosis", {})
        checks = {
            "diagnosis_status": diagnosis.get("diagnosis_status") == expected.get("diagnosis_status"),
            "fault_type": diagnosis.get("fault_type") == expected.get("fault_type"),
            "fault_device": diagnosis.get("fault_device") == expected.get("fault_device"),
            "fault_interface": diagnosis.get("fault_interface") == expected.get("fault_interface"),
        }
        for field in ("target_network", "target_ip", "next_hop"):
            if field in expected:
                checks[field] = diagnosis.get(field) == expected[field]
        trace = result.get("tool_trace", [])
        successful = [step for step in trace if step.get("action") in {"RUN_PING", "RUN_TRACERT", "CHECK_ROUTE", "CHECK_INTERFACE", "CHECK_ARP"} and step.get("result", {}).get("success")]
        rows.append({"case_id": scenario["case_id"], "passed": all(checks.values()), "checks": checks, "diagnosis": diagnosis, "tool_trace": trace, "turns": result.get("turns"), "elapsed_ms": round((time.perf_counter() - started) * 1000, 2), "successful_observations": len(successful), "replay_refs": sum(bool(step.get("result", {}).get("raw_ref")) for step in successful), "error": result.get("error")})
    passed = sum(row["passed"] for row in rows)
    return {"benchmark": "NetPath-Doctor Qwen Replay diagnosis benchmark", "model": client.config.model, "executor": "ReplayExecutor", "max_turns": max_turns, "max_tokens": max_tokens, "total": len(rows), "passed": passed, "failed": len(rows) - passed, "pass_rate": passed / len(rows) if rows else 0.0, "model_accuracy_claim": True, "cases": rows}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run real Qwen Replay diagnosis benchmark")
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, default=Path("reports/ai_trace/qwen_replay_benchmark_latest.json"))
    parser.add_argument("--max-turns", type=int, default=8)
    parser.add_argument("--max-tokens", type=int, default=768)
    args = parser.parse_args()
    report = run(args.repo_root, max_turns=args.max_turns, max_tokens=args.max_tokens)
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
