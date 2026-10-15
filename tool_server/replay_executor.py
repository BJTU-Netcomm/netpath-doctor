from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent.action_schema import AgentAction
from agent.command_mapper import build_execution_request
from parser.huawei_vrp import parse_cli_output


class ReplayExecutor:
    """Replay saved CLI logs and parse them as if a device returned them."""

    def __init__(
        self,
        scenario: dict[str, Any],
        action_catalog: dict[str, Any],
        case_dir: str | Path,
    ):
        self.scenario = scenario
        self.action_catalog = action_catalog
        self.case_dir = Path(case_dir)
        self.manifest = json.loads(
            (self.case_dir / "log_manifest.json").read_text(encoding="utf-8")
        )

    def capability_summary(self) -> dict[str, Any]:
        """Return safe availability metadata without exposing expected answers."""
        available: list[dict[str, Any]] = []
        for action_name, entries in self.manifest.get("actions", {}).items():
            if not isinstance(entries, dict):
                continue
            if "file" in entries:
                available.append({"action": action_name, "device": entries.get("device")})
                continue
            for key, entry in entries.items():
                if not isinstance(entry, dict):
                    continue
                item: dict[str, Any] = {"action": action_name}
                if entry.get("device"):
                    item["device"] = entry["device"]
                if ":" in key and entry.get("device"):
                    item["interface"] = key.split(":", 1)[1]
                available.append(item)
        return {
            "available_observations": available,
            "note": "Only listed action/device/interface combinations have replay logs; unsupported requests return an error.",
        }

    def execute(self, action: AgentAction) -> dict[str, Any]:
        request = build_execution_request(action, self.action_catalog)
        entry = self._lookup_entry(action)
        if entry is None:
            return {
                "success": False,
                "device": action.target_device,
                "vendor": self.scenario.get("vendor", "huawei_vrp"),
                "command": request["command"],
                "command_type": action.action,
                "facts": {},
                "raw_ref": None,
                "error": f"No replay log configured for {action.action}",
            }

        log_path = self.case_dir / entry["file"]
        text = log_path.read_text(encoding="utf-8")
        context = dict(self.manifest.get("context", {}))
        context.update(action.parameters)
        result = parse_cli_output(
            action.action,
            text,
            device=entry.get("device", action.target_device),
            vendor=self.scenario.get("vendor", "huawei_vrp"),
            context=context,
        )
        result["command"] = request["command"]
        # A replay result must remain distinguishable from a live device result.
        # The URI is stable within the case and does not expose machine paths.
        result["raw_ref"] = f"replay://{self.case_dir.name}/{entry['file']}"
        return result

    def _lookup_entry(self, action: AgentAction) -> dict[str, Any] | None:
        entries = self.manifest.get("actions", {}).get(action.action)
        if not isinstance(entries, dict):
            return None
        if "file" in entries:
            configured_device = entries.get("device")
            if configured_device and action.target_device and configured_device != action.target_device:
                return None
            return entries

        interface = action.parameters.get("interface")
        if action.target_device and interface:
            keyed = entries.get(f"{action.target_device}:{interface}")
            if isinstance(keyed, dict):
                return keyed
        if action.target_device:
            keyed = entries.get(action.target_device)
            if isinstance(keyed, dict):
                return keyed
        return None
