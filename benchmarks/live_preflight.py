from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Protocol

from tool_server.ensp_console_transport import ENSPConsoleTransport
from tool_server.ssh_transport import SSHTransport


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COMMAND = "display version"


class PreflightTransport(Protocol):
    devices: dict[str, dict[str, Any]]

    def send(self, device: str | None, command: str | None) -> str:
        ...


def probe_transport(
    transport: PreflightTransport,
    *,
    command: str = DEFAULT_COMMAND,
) -> dict[str, Any]:
    """Check every configured device without starting an Agent diagnosis."""
    device_results: list[dict[str, Any]] = []

    for device in sorted(transport.devices):
        try:
            output = transport.send(device, command)
            if not output.strip():
                raise ValueError("device returned empty output")
            device_results.append(
                {
                    "device": device,
                    "reachable": True,
                    "output_chars": len(output),
                    "error": None,
                }
            )
        except Exception as exc:  # Report every device even if one fails.
            device_results.append(
                {
                    "device": device,
                    "reachable": False,
                    "output_chars": 0,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )

    reachable = sum(result["reachable"] for result in device_results)
    total = len(device_results)
    return {
        "check": "eNSP CLI preflight",
        "command": command,
        "total": total,
        "reachable": reachable,
        "failed": total - reachable,
        "all_reachable": reachable == total,
        "devices": device_results,
    }


def run_preflight(
    device_config_path: str | Path,
    *,
    command: str = DEFAULT_COMMAND,
    raw_output_dir: str | Path | None = None,
    transport_kind: str = "ssh",
) -> dict[str, Any]:
    transport_class = {
        "ssh": SSHTransport,
        "ensp-console": ENSPConsoleTransport,
    }.get(transport_kind)
    if transport_class is None:
        raise ValueError(f"Unknown transport kind: {transport_kind}")
    transport = transport_class.from_json(device_config_path, capture_dir=raw_output_dir)
    return probe_transport(transport, command=command)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check SSH access to every configured eNSP device"
    )
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
    parser.add_argument(
        "--command",
        default=DEFAULT_COMMAND,
        help="Read-only VRP command used for the check",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "reports" / "live" / "preflight_latest.json",
        help="Machine-readable preflight report",
    )
    parser.add_argument(
        "--raw-output-dir",
        type=Path,
        default=REPO_ROOT / "reports" / "live" / "preflight_raw",
        help="Directory for raw CLI output",
    )
    args = parser.parse_args()

    result = run_preflight(
        args.devices,
        command=args.command,
        raw_output_dir=args.raw_output_dir,
        transport_kind=args.transport,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["all_reachable"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
