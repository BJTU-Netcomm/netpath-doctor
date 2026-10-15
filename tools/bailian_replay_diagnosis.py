"""Run one replay scenario through Qwen's read-only diagnosis harness.

This command deliberately uses ReplayExecutor. It proves the AI/tool protocol
without claiming that a replay log is a live eNSP result.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent.command_mapper import load_action_catalog
from ai.bailian_client import BailianClient
from ai.harness import AIHarness
from tool_server.replay_executor import ReplayExecutor


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("scenario", type=Path, help="path to a scenario.json")
    parser.add_argument("--output", type=Path, help="optional JSON report path")
    args = parser.parse_args()

    scenario_path = args.scenario.resolve()
    scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
    root = Path(__file__).resolve().parents[1]
    catalog = load_action_catalog(root / "rules" / "action_catalog.json")
    executor = ReplayExecutor(scenario, catalog, scenario_path.parent)
    client = BailianClient()
    result = AIHarness(client, executor, catalog).diagnose(scenario)
    try:
        scenario_label = str(scenario_path.relative_to(root))
    except ValueError:
        scenario_label = str(scenario_path)

    report = {
        "execution_mode": "ai_replay",
        "model": client.config.model,
        "scenario": scenario_label,
        "diagnosis": result.get("diagnosis"),
        "tool_trace": result.get("tool_trace", []),
        "turns": result.get("turns"),
        "error": result.get("error"),
        "valid_terminal_status": result.get("diagnosis", {}).get("diagnosis_status") in {"COMPLETED", "NORMAL", "NEED_MORE_DATA"},
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if report["valid_terminal_status"] and not result.get("error") else 1


if __name__ == "__main__":
    raise SystemExit(main())
