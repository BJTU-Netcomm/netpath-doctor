"""Run the read-only Qwen harness against a running eNSP or SSH transport.

This command performs observation only. Fault injection and recovery remain in
the outer live experiment controller and are intentionally unavailable here.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent.command_mapper import load_action_catalog
from ai.bailian_client import BailianClient
from ai.harness import AIHarness
from tool_server.ensp_console_transport import ENSPConsoleTransport
from tool_server.live_executor import LiveExecutor
from tool_server.ssh_transport import SSHTransport


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("scenario", type=Path, help="live scenario JSON")
    parser.add_argument("--transport", choices=("console", "ssh"), default="console")
    parser.add_argument("--devices", type=Path, help="console or SSH inventory JSON")
    parser.add_argument("--capture-dir", type=Path, default=Path("reports/live/ai_raw"))
    parser.add_argument("--output", type=Path, default=Path("reports/live/ai_diagnosis.json"))
    parser.add_argument("--max-turns", type=int, default=8)
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    scenario_path = args.scenario.resolve()
    scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
    catalog = load_action_catalog(root / "rules" / "action_catalog.json")
    inventory = (args.devices or (root / "config" / (
        "ensp_console.local.json" if args.transport == "console" else "devices.local.json"
    ))).resolve()

    if args.transport == "console":
        transport = ENSPConsoleTransport.from_json(inventory, capture_dir=args.capture_dir)
    else:
        transport = SSHTransport.from_json(inventory, capture_dir=args.capture_dir)

    client = BailianClient()
    executor = LiveExecutor(scenario, catalog, transport)
    result = AIHarness(client, executor, catalog, max_turns=args.max_turns).diagnose(scenario)
    try:
        scenario_label = str(scenario_path.relative_to(root))
    except ValueError:
        scenario_label = str(scenario_path)
    report = {
        "execution_mode": f"ai_live_{args.transport}",
        "model": client.config.model,
        "scenario": scenario_label,
        "diagnosis": result.get("diagnosis"),
        "tool_trace": result.get("tool_trace", []),
        "turns": result.get("turns"),
        "capture_dir": str(args.capture_dir),
        "writes_performed": False,
        "error": result.get("error"),
        "valid_terminal_status": result.get("diagnosis", {}).get("diagnosis_status") in {"COMPLETED", "NORMAL", "NEED_MORE_DATA"},
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if report["valid_terminal_status"] and not result.get("error") else 1


if __name__ == "__main__":
    raise SystemExit(main())
