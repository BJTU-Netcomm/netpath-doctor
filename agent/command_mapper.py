from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent.action_schema import AgentAction, validate_action


def load_action_catalog(catalog_path: str | Path) -> dict[str, Any]:
    path = Path(catalog_path)
    return json.loads(path.read_text(encoding="utf-8"))


def render_command(action: AgentAction, action_catalog: dict[str, Any]) -> str | None:
    validate_action(action, action_catalog)

    spec = action_catalog["actions"][action.action]
    template = spec.get("command_template")
    if template is None:
        return None

    values = dict(action.parameters)
    if action.target_device:
        values.setdefault("device", action.target_device)
    return template.format(**values)


def build_execution_request(action: AgentAction, action_catalog: dict[str, Any]) -> dict[str, Any]:
    return {
        "device": action.target_device,
        "command": render_command(action, action_catalog),
        "action": action.to_dict(),
    }
