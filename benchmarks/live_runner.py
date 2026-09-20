from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Protocol

from agent.command_mapper import load_action_catalog
from agent.state_machine import DiagnosisStateMachine
from tool_server.live_executor import LiveExecutor


REPO_ROOT = Path(__file__).resolve().parents[1]


class LiveTransport(Protocol):
    default_device: str

    def send(self, device: str | None, command: str | None) -> str:
        ...


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def diagnose_live_scenario(
    scenario: dict[str, Any],
    transport: LiveTransport,
) -> dict[str, Any]:
    scenario = dict(scenario)
    scenario.pop("ground_truth", None)
    scenario.pop("experiment_control", None)
    scenario.setdefault("source_device", transport.default_device)
    action_catalog = load_action_catalog(REPO_ROOT / "rules" / "action_catalog.json")
    executor = LiveExecutor(scenario, action_catalog, transport)
    return DiagnosisStateMachine().run(scenario, executor)


def run_live_case(
    scenario_path: str | Path,
    device_config_path: str | Path,
    *,
    raw_output_dir: str | Path | None = None,
    transport_kind: str = "ssh",
) -> dict[str, Any]:
    from tool_server.ensp_console_transport import ENSPConsoleTransport
    from tool_server.ssh_transport import SSHTransport

    transport_class = {
        "ssh": SSHTransport,
        "ensp-console": ENSPConsoleTransport,
    }.get(transport_kind)
    if transport_class is None:
        raise ValueError(f"Unknown transport kind: {transport_kind}")
    scenario = _read_json(Path(scenario_path))
    transport = transport_class.from_json(device_config_path, capture_dir=raw_output_dir)
    return diagnose_live_scenario(scenario, transport)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run one NetPath-Doctor scenario against live eNSP devices"
    )
    parser.add_argument("scenario", type=Path, help="Live scenario JSON path")
    parser.add_argument("--devices", type=Path, default=REPO_ROOT / "config" / "devices.local.json")
    parser.add_argument("--transport", choices=("ssh", "ensp-console"), default="ssh")
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
        transport_kind=args.transport,
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
