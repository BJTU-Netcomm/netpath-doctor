"""Bounded, read-only Qwen tool-calling harness for network diagnosis."""

from __future__ import annotations

import ipaddress
import json
import re
import time
from dataclasses import dataclass
from typing import Any, Mapping

from agent.action_schema import AgentAction, validate_action
from ai.bailian_client import BailianClient

ACTION_TO_TOOL = {
    "RUN_PING": "run_ping",
    "RUN_TRACERT": "run_tracert",
    "CHECK_ROUTE": "check_route",
    "CHECK_INTERFACE": "check_interface",
    "CHECK_ARP": "check_arp",
}
TERMINAL_ACTION_TO_TOOL = {"FINISH_DIAGNOSIS": "finish_diagnosis", "REQUEST_MORE_DATA": "request_more_data"}
TOOL_TO_ACTION = {**{tool: action for action, tool in ACTION_TO_TOOL.items()}, **{tool: action for action, tool in TERMINAL_ACTION_TO_TOOL.items()}}
_RESULT_KEYS = ("success", "facts", "raw_ref", "error")
_FAULT_TYPES = ["INTERFACE_DOWN", "ROUTE_MISSING", "ARP_UNRESOLVED", "NEXT_HOP_UNREACHABLE"]
_DIAGNOSIS_FIELDS = {"diagnosis_status", "fault_type", "fault_device", "fault_interface", "target_network", "evidence", "target_ip", "next_hop"}
_INTERFACE_RE = re.compile(r"^(?:GigabitEthernet|GE)\d+(?:/\d+){2}$", re.IGNORECASE)
_DEVICE_RE = re.compile(r"^R\d+$", re.IGNORECASE)


def build_read_only_tools(action_catalog: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Convert the frozen action catalog into OpenAI-compatible tool schemas."""
    tools: list[dict[str, Any]] = []
    for action_name, tool_name in ACTION_TO_TOOL.items():
        spec = action_catalog.get("actions", {}).get(action_name)
        if not isinstance(spec, Mapping) or not spec.get("read_only", False):
            raise ValueError(f"Required read-only action is missing or unsafe: {action_name}")
        properties: dict[str, Any] = {"device": {"type": "string", "description": "设备名，例如 R1、R2 或 R3"}}
        required: list[str] = ["device"]
        for parameter in spec.get("required_parameters", []):
            name = "target_ip" if parameter == "target_ip" else parameter
            properties[name] = {"type": "string"}
            required.append(name)
        tools.append({"type": "function", "function": {"name": tool_name, "description": spec.get("description", action_name), "parameters": {"type": "object", "properties": properties, "required": required, "additionalProperties": False}}})
    tools.extend([
        {"type": "function", "function": {"name": "finish_diagnosis", "description": "证据充分时结束诊断。只能提交已由工具事实支持的结果；evidence 只写最多4条、每条不超过120字符的事实摘要，不写长篇解释。", "parameters": {"type": "object", "properties": {"diagnosis": {"type": "object", "properties": {"diagnosis_status": {"type": "string", "enum": ["COMPLETED", "NORMAL"]}, "fault_type": {"type": ["string", "null"], "enum": _FAULT_TYPES + [None]}, "fault_device": {"type": ["string", "null"]}, "fault_interface": {"type": ["string", "null"]}, "target_network": {"type": ["string", "null"]}, "target_ip": {"type": ["string", "null"]}, "next_hop": {"type": ["string", "null"]}, "evidence": {"type": "array", "minItems": 1, "maxItems": 4, "items": {"type": "string", "maxLength": 120}}}, "required": ["diagnosis_status", "fault_type", "fault_device", "fault_interface", "evidence"], "additionalProperties": False}}, "required": ["diagnosis"], "additionalProperties": False}}},
        {"type": "function", "function": {"name": "request_more_data", "description": "证据不足时请求更多只读事实。", "parameters": {"type": "object", "properties": {"missing_fields": {"type": "array", "items": {"type": "string"}}}, "required": ["missing_fields"], "additionalProperties": False}}},
    ])
    return tools


def _normalize_result(result: Mapping[str, Any]) -> dict[str, Any]:
    normalized = {key: result.get(key) for key in _RESULT_KEYS}
    normalized["success"] = normalized["success"] is True
    normalized["facts"] = dict(normalized["facts"]) if isinstance(normalized["facts"], Mapping) else {}
    normalized["raw_ref"] = normalized["raw_ref"] or None
    normalized["error"] = normalized["error"] or None
    return normalized


def _parse_arguments(raw: Any) -> dict[str, Any]:
    if isinstance(raw, Mapping):
        return dict(raw)
    if not isinstance(raw, str):
        raise ValueError("tool arguments are not an object")
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("tool arguments are not a JSON object")
    return parsed


def _final_json(content: str) -> dict[str, Any] | None:
    content = content.strip()
    candidates = [content]
    if "```" in content:
        candidates.extend(part.strip() for part in content.split("```") if part.strip())
    for candidate in candidates:
        if candidate.startswith("json"):
            candidate = candidate[4:].lstrip()
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return _normalize_diagnosis(parsed)
    return None


def _normalize_diagnosis(diagnosis: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(diagnosis)
    if isinstance(normalized.get("diagnosis_status"), str):
        normalized["diagnosis_status"] = normalized["diagnosis_status"].upper()
    if isinstance(normalized.get("fault_type"), str):
        normalized["fault_type"] = normalized["fault_type"].upper()
    return normalized


def _need_more_data(reason: str) -> dict[str, Any]:
    return {"diagnosis_status": "NEED_MORE_DATA", "fault_type": None, "fault_device": None, "fault_interface": None, "target_network": None, "evidence": [reason]}


def _safe_public_scenario(scenario: Mapping[str, Any]) -> dict[str, Any]:
    allowed = ("source_device", "source_ip", "destination_ip", "destination_network", "vendor")
    result = {key: scenario[key] for key in allowed if key in scenario}
    result["allowed_devices"] = ["R1", "R2", "R3"]
    return result


def _safe_capability_summary(executor: Any) -> dict[str, Any] | None:
    """Expose only replay/live tool availability, never answers or raw logs."""
    provider = getattr(executor, "capability_summary", None)
    if not callable(provider):
        return None
    summary = provider()
    if not isinstance(summary, Mapping):
        return None
    # Keep this prompt data small and declarative.  The executor remains the
    # source of truth and still rejects every unsupported request locally.
    return {str(key): value for key, value in summary.items() if key in {"available_observations", "note"}}


def _validate_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or any(ord(ch) < 32 for ch in value):
        raise ValueError(f"{field} must be a non-empty single-line string")
    return value


def _validate_ipv4(value: Any, field: str) -> str:
    value = _validate_text(value, field)
    try:
        ipaddress.IPv4Address(value)
    except ipaddress.AddressValueError as exc:
        raise ValueError(f"{field} must be an IPv4 address without CIDR") from exc
    return value


def _validate_diagnosis(diagnosis: Any, observations: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, list[str]]:
    if not isinstance(diagnosis, Mapping):
        return None, ["diagnosis must be an object"]
    value = _normalize_diagnosis(diagnosis)
    errors = [f"unsupported diagnosis field: {name}" for name in sorted(set(value) - _DIAGNOSIS_FIELDS)]
    status = value.get("diagnosis_status")
    if status not in {"COMPLETED", "NORMAL"}:
        errors.append("diagnosis_status must be COMPLETED or NORMAL")
    if value.get("fault_type") not in _FAULT_TYPES + [None]:
        errors.append("fault_type is outside the V1 catalog")
    evidence = value.get("evidence")
    if not isinstance(evidence, list) or not evidence or not all(isinstance(item, str) and item.strip() for item in evidence):
        errors.append("evidence must contain at least one non-empty string")
    elif len(evidence) > 4 or any(len(item) > 120 for item in evidence):
        errors.append("evidence must contain at most 4 strings of at most 120 characters")
    successful = [item for item in observations if item.get("result", {}).get("success")]
    if status == "NORMAL":
        if any(value.get(field) is not None for field in ("fault_type", "fault_device", "fault_interface")):
            errors.append("NORMAL diagnosis must not contain a fault")
        if not any(item.get("action") == "RUN_PING" and item["result"]["facts"].get("reachable") is True for item in successful):
            errors.append("NORMAL requires a successful reachable ping observation")
    elif status == "COMPLETED":
        device = value.get("fault_device")
        if not isinstance(device, str) or not _DEVICE_RE.fullmatch(device):
            errors.append("COMPLETED diagnosis requires a valid fault_device")
        fault_type = value.get("fault_type")
        if fault_type == "INTERFACE_DOWN":
            if not any(item.get("action") == "CHECK_INTERFACE" and item.get("target_device") == device and item["result"]["facts"].get("physical_status") == "DOWN" and (value.get("fault_interface") is None or item["result"]["facts"].get("interface") == value.get("fault_interface")) for item in successful):
                errors.append("INTERFACE_DOWN requires a matching successful interface DOWN observation")
        elif fault_type == "ROUTE_MISSING":
            if value.get("fault_interface") is not None:
                errors.append("ROUTE_MISSING fault_interface must be null")
            if not any(item.get("action") == "CHECK_ROUTE" and item.get("target_device") == device and item["result"]["facts"].get("route_found") is False for item in successful):
                errors.append("ROUTE_MISSING requires a matching route_found=false observation")
            if any(
                item.get("action") == "CHECK_INTERFACE"
                and item.get("target_device") == device
                and item["result"]["facts"].get("physical_status") == "DOWN"
                for item in successful
            ):
                errors.append(
                    "ROUTE_MISSING is invalid when the fault device has a physical interface DOWN; "
                    "classify the primary fault as INTERFACE_DOWN"
                )
        elif fault_type == "ARP_UNRESOLVED":
            if not any(item.get("action") == "CHECK_ARP" and item.get("target_device") == device and item["result"]["facts"].get("entry_found") is False for item in successful):
                errors.append("ARP_UNRESOLVED requires a matching ARP entry_found=false observation")
        elif fault_type == "NEXT_HOP_UNREACHABLE":
            routes = [item for item in successful if item.get("action") == "CHECK_ROUTE" and item.get("target_device") == device and item["result"]["facts"].get("route_found") is True]
            if not routes:
                errors.append("NEXT_HOP_UNREACHABLE requires a matching route observation")
            if not any(item.get("action") == "CHECK_ARP" and item.get("target_device") == device and item["result"]["facts"].get("entry_found") is False for item in successful):
                errors.append("NEXT_HOP_UNREACHABLE requires an unresolved next-hop ARP observation")
            if value.get("next_hop") and routes and value["next_hop"] != routes[-1]["result"]["facts"].get("next_hop"):
                errors.append("next_hop does not match the observed route")
        else:
            errors.append("COMPLETED diagnosis requires a fault_type")
    return (value if not errors else None), errors


@dataclass
class AIHarness:
    client: BailianClient
    executor: Any
    action_catalog: Mapping[str, Any]
    max_turns: int = 8
    max_tool_calls: int = 24
    max_tokens: int = 768

    def diagnose(self, scenario: Mapping[str, Any]) -> dict[str, Any]:
        tools = build_read_only_tools(self.action_catalog)
        system_prompt = (
            "你是网络故障诊断 Agent。只能调用已注册的只读工具获取事实，不能执行配置、删除、恢复、shutdown 或 shell 命令。"
            "只能使用当前回放/现场能力摘要中列出的设备和观察项，不能为了试探而调用不存在的设备或日志。"
            "参数必须包含设备名和合法 IPv4/接口名。证据不足时必须调用 request_more_data；证据充分时必须调用 finish_diagnosis。"
            "最终诊断必须完全由成功工具返回的 facts 支持，不要根据场景标题或猜测作答。"
            "如果同一故障设备的相关以太网接口 physical_status 为 DOWN，必须优先诊断为 INTERFACE_DOWN；接口关闭导致的路由撤销属于次生现象，不能仅凭 route_found=false 判为 ROUTE_MISSING。"
            "finish_diagnosis 必须使用紧凑 JSON：evidence 最多4条、每条不超过120个字符，只写事实摘要，不重复长篇回显。"
        )
        public_scenario = _safe_public_scenario(scenario)
        capabilities = _safe_capability_summary(self.executor)
        if capabilities:
            public_scenario["capabilities"] = capabilities
        messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}, {"role": "user", "content": "请诊断以下场景，并按需要调用工具：\n" + json.dumps(public_scenario, ensure_ascii=False)}]
        trace: list[dict[str, Any]] = []
        observations: list[dict[str, Any]] = []
        turns = 0
        tool_calls = 0
        for _ in range(self.max_turns):
            turns += 1
            try:
                response = self.client.chat(messages, tools=tools, max_tokens=self.max_tokens)
            except RuntimeError as exc:
                return {"diagnosis": _need_more_data(f"AI provider unavailable: {exc}"), "raw_content": "", "tool_trace": trace, "turns": turns, "error": "provider"}
            message = ((response.get("choices") or [{}])[0].get("message") or {})
            calls = message.get("tool_calls") or []
            if not calls:
                content = message.get("content") or ""
                diagnosis = _final_json(content)
                if diagnosis is None:
                    diagnosis = _need_more_data("AI returned no structured diagnosis")
                else:
                    valid, errors = _validate_diagnosis(diagnosis, observations)
                    if valid is None:
                        diagnosis = _need_more_data("; ".join(errors))
                return {"diagnosis": diagnosis, "raw_content": content, "tool_trace": trace, "turns": turns}
            messages.append({"role": "assistant", "content": message.get("content"), "tool_calls": calls})
            for call in calls:
                tool_calls += 1
                if tool_calls > self.max_tool_calls:
                    return {"diagnosis": _need_more_data("AI tool-call budget reached"), "raw_content": "", "tool_trace": trace, "turns": turns, "error": "tool_budget"}
                function = call.get("function") or {}
                tool_name = function.get("name")
                action_name = TOOL_TO_ACTION.get(tool_name)
                call_id = call.get("id", f"call-{tool_calls}")
                started = time.perf_counter()
                arguments: dict[str, Any] = {}
                terminal_diagnosis: dict[str, Any] | None = None
                try:
                    arguments = _parse_arguments(function.get("arguments", "{}"))
                    if not action_name:
                        raise ValueError("unknown tool")
                    if action_name == "FINISH_DIAGNOSIS":
                        if set(arguments) != {"diagnosis"}:
                            raise ValueError("finish_diagnosis accepts only diagnosis")
                        terminal_diagnosis, errors = _validate_diagnosis(arguments["diagnosis"], observations)
                        if terminal_diagnosis is None:
                            raise ValueError("; ".join(errors))
                        result = _normalize_result({"success": True, "facts": terminal_diagnosis, "raw_ref": None, "error": None})
                    elif action_name == "REQUEST_MORE_DATA":
                        missing = arguments.get("missing_fields")
                        if set(arguments) != {"missing_fields"} or not isinstance(missing, list) or not missing or not all(isinstance(item, str) and item.strip() for item in missing):
                            raise ValueError("missing_fields must be a non-empty string array")
                        terminal_diagnosis = _need_more_data("missing_fields: " + ", ".join(missing))
                        result = _normalize_result({"success": True, "facts": terminal_diagnosis, "raw_ref": None, "error": None})
                    else:
                        target_device, params = self._validate_observation_arguments(action_name, arguments, scenario)
                        action = AgentAction(action=action_name, target_device=target_device, parameters=params, reason="Qwen read-only observation")
                        validate_action(action, dict(self.action_catalog))
                        result = _normalize_result(self.executor.execute(action))
                        observations.append({"action": action_name, "target_device": target_device, "parameters": params, "result": result})
                except (ValueError, TypeError, json.JSONDecodeError) as exc:
                    result = _normalize_result({"success": False, "facts": {}, "raw_ref": None, "error": str(exc)})
                    if action_name in {"FINISH_DIAGNOSIS", "REQUEST_MORE_DATA"}:
                        # A truncated JSON tool call can be retried by the
                        # model after seeing the local validation error. Other
                        # validation failures stop safely as NEED_MORE_DATA.
                        if isinstance(exc, json.JSONDecodeError):
                            terminal_diagnosis = None
                        else:
                            terminal_diagnosis = _need_more_data(f"terminal action rejected: {exc}")
                trace.append({"call_id": call_id, "tool": tool_name, "action": action_name, "arguments": arguments, "device": arguments.get("device"), "result": result, "elapsed_ms": round((time.perf_counter() - started) * 1000, 2)})
                messages.append({"role": "tool", "tool_call_id": call_id, "name": tool_name or "unknown", "content": json.dumps(result, ensure_ascii=False)})
                if terminal_diagnosis is not None:
                    return {"diagnosis": terminal_diagnosis, "raw_content": "", "tool_trace": trace, "turns": turns}
        return {"diagnosis": _need_more_data("AI tool-call turn limit reached"), "raw_content": "", "tool_trace": trace, "turns": turns, "error": "turn_budget"}

    def _validate_observation_arguments(self, action_name: str, arguments: Mapping[str, Any], scenario: Mapping[str, Any]) -> tuple[str, dict[str, str]]:
        spec = self.action_catalog.get("actions", {}).get(action_name, {})
        required = {"target_ip" if item == "target_ip" else item for item in spec.get("required_parameters", [])}
        expected = required | {"device"}
        if set(arguments) != expected:
            raise ValueError(f"invalid {action_name} arguments; missing={sorted(expected - set(arguments))}, extra={sorted(set(arguments) - expected)}")
        device = _validate_text(arguments["device"], "device")
        allowed = {"R1", "R2", "R3"}
        if isinstance(scenario.get("allowed_devices"), list):
            allowed = {str(item) for item in scenario["allowed_devices"]}
        if device not in allowed or not _DEVICE_RE.fullmatch(device):
            raise ValueError(f"device must be one of {sorted(allowed)}")
        params: dict[str, str] = {}
        for name in required:
            value = arguments[name]
            if name in {"target_ip", "destination"}:
                params[name] = _validate_ipv4(value, name)
            elif name == "interface":
                params[name] = _validate_text(value, name)
                if not _INTERFACE_RE.fullmatch(params[name]):
                    raise ValueError("interface must be a Huawei Ethernet interface")
            else:
                params[name] = _validate_text(value, name)
        return device, params
