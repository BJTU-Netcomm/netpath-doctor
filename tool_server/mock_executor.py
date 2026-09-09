from __future__ import annotations

from typing import Any

from agent.action_schema import AgentAction
from agent.command_mapper import build_execution_request


class MockExecutor:
    def __init__(self, scenario: dict[str, Any], action_catalog: dict[str, Any]):
        self.scenario = scenario
        self.action_catalog = action_catalog

    def execute(self, action: AgentAction) -> dict[str, Any]:
        request = build_execution_request(action, self.action_catalog)
        facts = self._lookup_facts(action)
        return {
            "success": True,
            "device": action.target_device,
            "vendor": self.scenario.get("vendor", "huawei_vrp"),
            "command": request["command"],
            "command_type": action.action,
            "facts": facts,
            "error": None,
        }

    def _lookup_facts(self, action: AgentAction) -> dict[str, Any]:
        outputs = self.scenario.get("mock_outputs", {})
        action_outputs = outputs.get(action.action)
        if action_outputs is None:
            return {}

        if isinstance(action_outputs, dict) and action.target_device:
            interface = action.parameters.get("interface")
            if interface:
                key = f"{action.target_device}:{interface}"
                if key in action_outputs:
                    return action_outputs[key]
            if action.target_device in action_outputs:
                return action_outputs[action.target_device]

        return action_outputs if isinstance(action_outputs, dict) else {}
