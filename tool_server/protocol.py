from __future__ import annotations

from typing import Any, Protocol

from agent.action_schema import AgentAction


class Executor(Protocol):
    """接口：状态机只依赖 execute，不依赖具体设备连接方式。"""

    def execute(self, action: AgentAction) -> dict[str, Any]:
        ...


def is_successful_result(result: dict[str, Any]) -> bool:
    """统一判断 Tool Server/Parser 返回是否可供 Agent 使用。"""
    return result.get("success") is True and isinstance(result.get("facts"), dict)
