from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentAction:
    action: str
    target_device: str | None = None
    parameters: dict[str, Any] = field(default_factory=dict)
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "target_device": self.target_device,
            "parameters": self.parameters,
            "reason": self.reason,
        }


def validate_action(action: AgentAction, action_catalog: dict[str, Any]) -> None:
    actions = action_catalog.get("actions", {})
    if action.action not in actions:
        raise ValueError(f"Unknown action: {action.action}")

    spec = actions[action.action]
    if not spec.get("read_only", False):
        raise ValueError(f"Action is not read-only: {action.action}")

    missing = []
    if spec.get("target_device_required", False) and not action.target_device:
        missing.append("target_device")

    for name in spec.get("required_parameters", []):
        value = action.parameters.get(name)
        if value is None or value == "" or value == [] or value == {}:
            missing.append(name)

    if missing:
        raise ValueError(f"Missing required parameters for {action.action}: {', '.join(missing)}")
