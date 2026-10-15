from __future__ import annotations

from typing import Any, Protocol

from agent.action_schema import AgentAction
from agent.command_mapper import build_execution_request
from parser.huawei_vrp import parse_cli_output


class CommandTransport(Protocol):
    """真实 CLI Server、SSH 或仿真器都可以实现这个最小发送接口。"""

    def send(self, device: str | None, command: str | None) -> str:
        ...


class LiveExecutor:
    """把 Agent 动作发送到外部 CLI 传输层并解析设备回显。"""

    def __init__(
        self,
        scenario: dict[str, Any],
        action_catalog: dict[str, Any],
        transport: CommandTransport,
    ) -> None:
        self.scenario = scenario
        self.action_catalog = action_catalog
        self.transport = transport

    def execute(self, action: AgentAction) -> dict[str, Any]:
        request = build_execution_request(action, self.action_catalog)
        device = request["device"] or self.scenario.get("source_device")
        try:
            raw_output = self.transport.send(device, request["command"])
        except Exception as exc:  # transport errors are data for the state machine
            return {
                "success": False,
                "device": device,
                "vendor": self.scenario.get("vendor", "huawei_vrp"),
                "command": request["command"],
                "command_type": action.action,
                "facts": {},
                "raw_ref": None,
                "error": f"CLI transport error: {exc}",
            }

        context = dict(self.scenario.get("parser_context", {}))
        if "ip_to_device" in self.scenario:
            context.setdefault("ip_to_device", self.scenario["ip_to_device"])
        context.update(action.parameters)
        result = parse_cli_output(
            action.action,
            raw_output,
            device=device,
            vendor=self.scenario.get("vendor", "huawei_vrp"),
            context=context,
        )
        result["command"] = request["command"]
        # Transports may expose a capture reference (for example a local
        # console capture file). Keep it optional so old transports continue
        # to work unchanged.
        capture_ref = getattr(self.transport, "last_raw_ref", None)
        result["raw_ref"] = capture_ref
        return result
