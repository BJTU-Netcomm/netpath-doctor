from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from agent.command_mapper import load_action_catalog
from agent.state_machine import DiagnosisStateMachine
from tool_server.live_executor import LiveExecutor
from tool_server.ssh_transport import SSHTransport


REPO_ROOT = Path(__file__).resolve().parents[1]


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def run_live_case(
    scenario_path: str | Path,
    device_config_path: str | Path,
    *,
    raw_output_dir: str | Path | None = None,
) -> dict[str, Any]:
    scenario = _read_json(Path(scenario_path))
    scenario.pop("ground_truth", None)
    transport = SSHTransport.from_json(
        device_config_path,
        capture_dir=raw_output_dir,
    )
    scenario.setdefault("source_device", transport.default_device)
    action_catalog = load_action_catalog(REPO_ROOT / "rules" / "action_catalog.json")
    executor = LiveExecutor(scenario, action_catalog, transport)
    return DiagnosisStateMachine().run(scenario, executor)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run one NetPath-Doctor scenario against live eNSP devices"
    )
    parser.add_argument("scenario", type=Path, help="Live scenario JSON path")
    parser.add_argument(
        "--devices",
        type=Path,
        default=REPO_ROOT / "config" / "devices.local.json",
        help="Local SSH device inventory",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "reports" / "live" / "latest.json",
        help="Diagnosis report path",
    )
    parser.add_argument(
        "--raw-output-dir",
        type=Path,
        default=REPO_ROOT / "reports" / "live" / "raw",
        help="Directory for raw CLI output",
    )
    args = parser.parse_args()

    result = run_live_case(
        args.scenario,
        args.devices,
        raw_output_dir=args.raw_output_dir,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("diagnosis_status") != "NEED_MORE_DATA" else 1


if __name__ == "__main__":
    raise SystemExit(main())
