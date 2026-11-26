"""Connect the browser to read-only diagnosis and preset eNSP fault controls."""

from __future__ import annotations

import ipaddress
import json
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from agent.command_mapper import load_action_catalog, render_command
from ai.harness import AIHarness, ACTION_TO_TOOL
from tool_server.ensp_console_transport import ENSPConsoleTransport
from tool_server.live_executor import LiveExecutor
from parser.huawei_vrp import parse_cli_output

EventCallback = Callable[[dict[str, Any]], None]
READ_ONLY_COMMAND = re.compile(
    r"(?:ping (?:\d{1,3}\.){3}\d{1,3}|tracert -m 3 -q 1 -w 1000 (?:\d{1,3}\.){3}\d{1,3}|"
    r"display ip routing-table(?: (?:\d{1,3}\.){3}\d{1,3})?|"
    r"display interface (?:GigabitEthernet|GE)\d+/\d+/\d+|"
    r"display arp(?: (?:\d{1,3}\.){3}\d{1,3})?|display ip interface brief)"
)
CONFIG_ERROR_PATTERN = re.compile(r"(?im)^\s*(?:error:|%)")
FAULT_TYPES = {"INTERFACE_DOWN", "ROUTE_MISSING"}
ROUTE_INJECT_COMMAND = "undo ip route-static 192.168.3.0 255.255.255.0 10.0.23.2"
ROUTE_RECOVERY_COMMAND = "ip route-static 192.168.3.0 255.255.255.0 10.0.23.2"


class ReadOnlyConsole:
    """A small adapter with no configuration methods or arbitrary CLI entry."""

    def __init__(self, transport):
        self.transport = transport
        self.last_raw_output = ""
        self.last_raw_ref = None

    def send(self, device, command):
        self.last_raw_output = ""
        self.last_raw_ref = None
        if not isinstance(command, str) or not READ_ONLY_COMMAND.fullmatch(command):
            raise ValueError("网页诊断仅允许注册的只读观察命令。")
        # Older VRP builds reject `display arp <ip>`. Retrieve a complete,
        # bounded table and keep target_ip selection in the existing parser.
        if command.startswith("display arp "):
            command = "display arp"
        raw = self.transport.send(device, command)
        self.last_raw_output = raw
        self.last_raw_ref = self.transport.last_raw_ref
        return raw


class TracedLiveExecutor:
    def __init__(self, scenario, catalog, transport, topology, emit):
        self.catalog = catalog
        self.transport = ReadOnlyConsole(transport)
        self.executor = LiveExecutor(scenario, catalog, self.transport)
        self.topology = topology
        self.emit = emit
        self.command_trace = []

    def capability_summary(self):
        observations = []
        for device, settings in self.topology["devices"].items():
            for action in ("RUN_PING", "RUN_TRACERT", "CHECK_ROUTE", "CHECK_ARP"):
                observations.append({"action": action, "device": device})
            for interface in settings["interfaces"]:
                observations.append({"action": "CHECK_INTERFACE", "device": device, "interface": interface})
        return {"available_observations": observations,
                "note": "现场仅检查拓扑内已连接的业务接口，不能把闲置接口 DOWN 当作故障。" +
                        "先检查源设备到目标的 ping；若可达，可报告本次探测正常；若失败，检查路径、路由和相关链路接口，再定位原因。" +
                        "若首轮 ping 可达但有少量丢包，优先从同一源设备复测同一目标，并在结论中保留首轮与复测丢包率；不要仅因一次丢包就认定链路故障。" +
                        json.dumps(self.topology, ensure_ascii=False)}

    def execute(self, action):
        if action.action not in ACTION_TO_TOOL:
            raise ValueError("现场执行器只接受五类只读观察。")
        device = action.target_device
        if device not in self.topology["devices"]:
            raise ValueError("设备不在当前拓扑中。")
        if action.action == "CHECK_INTERFACE":
            interface = action.parameters.get("interface", "")
            interface = re.sub(r"^GE", "GigabitEthernet", interface)
            if interface not in self.topology["devices"][device]["interfaces"]:
                raise ValueError("只检查当前拓扑已连接的接口，拒绝检查闲置或未知接口。")
        requested_command = render_command(action, self.catalog)
        command = "display arp" if action.action == "CHECK_ARP" else requested_command
        self.emit({"event": "tool_start", "device": device, "action": action.action, "command": command})
        result = self.executor.execute(action)
        result["command"] = command
        record = {"device": device, "action": action.action, "command": command,
                  "requested_command": requested_command,
                  "success": result.get("success") is True, "facts": result.get("facts", {}),
                  "error": result.get("error"), "raw_ref": result.get("raw_ref"),
                  "raw_output": self.transport.last_raw_output[:16000]}
        self.command_trace.append(record)
        self.emit({"event": "tool_result", **record})
        return result


class LiveConsoleService:
    def __init__(self, root: Path):
        self.root = root
        self.inventory = root / "config" / "ensp_console.local.json"
        self.topology_path = root / "config" / "diagnosis_topology.json"

    def topology(self):
        return json.loads(self.topology_path.read_text(encoding="utf-8"))

    def summary(self):
        topo = self.topology()
        return {"configured": self.inventory.exists(), "name": topo["name"],
                "devices": list(topo["devices"]), "source": topo["default_source"],
                "target_ip": topo["default_target"], "read_only_diagnosis": True,
                "preset_fault_control": True}

    def transport(self, capture_dir=None):
        return ENSPConsoleTransport.from_json(self.inventory, capture_dir=capture_dir,
                                             connect_timeout=3, read_timeout=15)

    def inject_fault(self, fault_type):
        if fault_type not in FAULT_TYPES:
            raise ValueError("请选择支持的故障类型。")
        topology = self.topology()
        source = topology["default_source"]
        target = topology["default_target"]
        transport = self.transport()
        baseline = self._read(transport, "RUN_PING", source, f"ping {target}")
        if not baseline["success"] or not baseline["facts"].get("reachable"):
            raise ValueError("基线连通性检查未通过，未注入故障。请先恢复网络并确认目标可达。")

        device = "R2"
        interface = "GigabitEthernet0/0/1" if fault_type == "INTERFACE_DOWN" else None
        route = self._read(transport, "CHECK_ROUTE", device,
                           f"display ip routing-table {target}", {"destination": target})
        if not route["success"] or not route["facts"].get("route_found"):
            raise ValueError("R2 目标路由当前不可用，未注入故障。")

        if fault_type == "INTERFACE_DOWN":
            if route["facts"].get("out_interface") != interface:
                raise ValueError("R2 当前出接口与预设实验拓扑不一致，未注入故障。")
            state = self._read(transport, "CHECK_INTERFACE", device,
                               f"display interface {interface}", {"interface": interface})
            facts = state["facts"]
            if not state["success"] or facts.get("physical_status") != "UP" or facts.get("protocol_status") != "UP":
                raise ValueError("R2 实验接口当前不是 UP/UP，未覆盖现有网络状态。")
            commands = [f"interface {interface}", "shutdown"]
        else:
            facts = route["facts"]
            if facts.get("destination") != "192.168.3.0/24" or facts.get("next_hop") != "10.0.23.2":
                raise ValueError("R2 目标路由与预设实验拓扑不一致，未修改配置。")
            commands = [ROUTE_INJECT_COMMAND]

        try:
            config_output = transport.send_config(device, commands)
        except Exception as exc:
            recovery = self._recover_fault(transport, fault_type, device, target, interface)
            if recovery["success"]:
                raise RuntimeError("故障注入命令执行异常，已确认恢复到注入前状态。") from exc
            raise RuntimeError("故障注入命令执行异常，恢复状态未确认，请立即检查设备。") from exc
        if CONFIG_ERROR_PATTERN.search(config_output):
            raise RuntimeError("设备拒绝了故障注入命令，网络状态需要重新检测。")
        verification = self._read_fault_state(transport, fault_type, device, target, interface)
        if not verification["active"]:
            recovery = self._recover_fault(transport, fault_type, device, target, interface)
            raise RuntimeError("故障注入未通过设备回显验证。已尝试恢复。" if recovery["success"]
                               else "故障注入未通过验证，且自动恢复未确认成功，请立即检查设备状态。")

        return {"fault_type": fault_type, "device": device, "interface": interface,
                "active": True, "message": "故障已注入并通过设备回显验证。",
                "baseline": baseline, "verification": verification, "writes_performed": True}

    def recover_fault(self, fault_type):
        if fault_type not in FAULT_TYPES:
            raise ValueError("请选择支持的故障类型。")
        target = self.topology()["default_target"]
        device = "R2"
        interface = "GigabitEthernet0/0/1" if fault_type == "INTERFACE_DOWN" else None
        recovery = self._recover_fault(self.transport(), fault_type, device, target, interface)
        if not recovery["success"]:
            raise RuntimeError(recovery["error"] or "设备未确认故障恢复，请检查设备状态。")
        return {"fault_type": fault_type, "device": device, "interface": interface,
                "active": False, "message": "恢复命令已执行并通过设备回显验证。",
                "verification": recovery["verification"], "writes_performed": True}

    @staticmethod
    def _read(transport, action, device, command, context=None):
        raw = transport.send(device, command)
        parsed = parse_cli_output(action, raw, device=device, context=context or {})
        return {"command": command, "success": parsed["success"],
                "facts": parsed["facts"], "error": parsed["error"], "raw_output": raw}

    def _read_fault_state(self, transport, fault_type, device, target, interface):
        if fault_type == "INTERFACE_DOWN":
            check = self._read(transport, "CHECK_INTERFACE", device,
                               f"display interface {interface}", {"interface": interface})
            facts = check["facts"]
            active = (check["success"] and facts.get("physical_status") == "DOWN"
                      and facts.get("protocol_status") == "DOWN")
            recovered = (check["success"] and facts.get("physical_status") == "UP"
                         and facts.get("protocol_status") == "UP")
        else:
            check = self._read(transport, "CHECK_ROUTE", device,
                               f"display ip routing-table {target}", {"destination": target})
            facts = check["facts"]
            active = check["success"] and facts.get("route_found") is False
            recovered = check["success"] and facts.get("route_found") is True
        return {"active": active, "recovered": recovered, "check": check, "facts": facts}

    def _recover_fault(self, transport, fault_type, device, target, interface):
        commands = ([f"interface {interface}", "undo shutdown"]
                    if fault_type == "INTERFACE_DOWN" else [ROUTE_RECOVERY_COMMAND])
        errors = []
        verification = None
        for _attempt in range(3):
            try:
                output = transport.send_config(device, commands)
            except Exception as exc:
                errors.append(f"恢复命令异常：{type(exc).__name__}")
                continue
            if CONFIG_ERROR_PATTERN.search(output):
                errors.append("设备拒绝恢复命令")
                continue
            time.sleep(0.5)
            try:
                verification = self._read_fault_state(transport, fault_type, device, target, interface)
            except Exception as exc:
                errors.append(f"恢复状态读取失败：{type(exc).__name__}")
                continue
            if verification["recovered"]:
                return {"success": True, "verification": verification, "error": None}
            errors.append("设备回显仍显示故障存在或状态无法解析")
        return {"success": False, "verification": verification, "error": "; ".join(errors)}

    def preflight(self, emit: EventCallback | None = None):
        emit = emit or (lambda _: None)
        transport = ReadOnlyConsole(self.transport())
        checks = []
        for device in self.topology()["devices"]:
            emit({"event": "progress", "message": f"检查 {device} Console：display ip interface brief"})
            try:
                raw = transport.send(device, "display ip interface brief")
                success = "Interface" in raw and "Physical" in raw and "Protocol" in raw
                error = None if success else "设备未返回可识别的接口摘要，请检查启动状态。"
            except Exception as exc:
                raw, success, error = "", False, str(exc)
            checks.append({"device": device, "ready": success, "error": error, "raw_output": raw[:16000]})
        return {"ready": all(item["ready"] for item in checks), "devices": checks, "writes_performed": False}

    def diagnose(self, *, source, target_ip, question, client, emit: EventCallback | None = None):
        emit = emit or (lambda _: None)
        topo = self.topology()
        if not isinstance(source, str) or source not in topo["devices"]:
            raise ValueError("请选择当前拓扑中的源路由器。")
        try:
            address = ipaddress.IPv4Address(target_ip)
        except (ipaddress.AddressValueError, TypeError) as exc:
            raise ValueError("目标必须是合法 IPv4 地址，不含端口或掩码。") from exc
        if address.is_multicast or address.is_unspecified or address == ipaddress.IPv4Address('255.255.255.255'):
            raise ValueError("目标应为可探测的单播 IPv4 地址。")
        if not isinstance(question, str) or len(question) > 8000:
            raise ValueError("问题必须是 8000 字符以内的文字。")
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:8]
        folder = self.root / "reports" / "ui_live" / run_id
        folder.mkdir(parents=True, exist_ok=True)
        catalog = load_action_catalog(self.root / "rules" / "action_catalog.json")
        mapping = {ip: name for name, config in topo["devices"].items() for ip in config["interfaces"].values()}
        scenario = {"source_device": source, "destination_ip": str(address), "vendor": "huawei_vrp",
                    "allowed_devices": list(topo["devices"]), "ip_to_device": mapping}
        executor = TracedLiveExecutor(scenario, catalog, self.transport(folder / "raw"), topo, emit)
        started = time.perf_counter()
        emit({"event": "progress", "message": f"已受理：从 {source} 检查 {address}；只读模式，不预设存在故障。"})
        result = AIHarness(client, executor, catalog, max_turns=8, max_tool_calls=24,
                           max_tokens=1024, on_event=emit, max_seconds=360).diagnose(scenario, question=question)
        report = {"execution_mode": "ai_live_console", "run_id": run_id,
                  "created_at": datetime.now(timezone.utc).isoformat(), "source_device": source,
                  "target_ip": str(address), "model": client.config.model,
                  "diagnosis": result["diagnosis"], "tool_trace": result.get("tool_trace", []),
                  "command_trace": executor.command_trace, "turns": result.get("turns"),
                  "error": result.get("error"), "writes_performed": False,
                  "live_checks_performed": bool(executor.command_trace),
                  "elapsed_ms": round((time.perf_counter() - started) * 1000)}
        # The question and client credentials are deliberately absent from this report.
        # Provider errors may quote their request; scrub the credential if present.
        rendered = json.dumps(report, ensure_ascii=False, indent=2)
        if client.config.api_key:
            rendered = rendered.replace(client.config.api_key, "[redacted]")
        report = json.loads(rendered)
        (folder / "report.json").write_text(rendered, encoding="utf-8")
        return report
