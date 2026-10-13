from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agent.action_schema import AgentAction


@dataclass
class DiagnosisContext:
    case_id: str
    scenario: dict[str, Any]
    evidence: list[str] = field(default_factory=list)
    actions: list[dict[str, Any]] = field(default_factory=list)


class DiagnosisStateMachine:
    def run(self, scenario: dict[str, Any], executor: Any) -> dict[str, Any]:
        context = DiagnosisContext(case_id=scenario["case_id"], scenario=scenario)

        ping_result = self._run_action(
            context,
            executor,
            AgentAction(
                action="RUN_PING",
                parameters={"target_ip": scenario["destination_ip"]},
                reason="初始连通性检查",
            ),
        )
        if not ping_result.get("success"):
            return self._request_more_data(context, ["ping_facts"])
        if ping_result["facts"].get("reachable"):
            context.evidence.append("ping 成功")
            return self._finish_normal(context)

        packet_loss = ping_result["facts"].get("packet_loss")
        if packet_loss == 100:
            context.evidence.append("ping 100% 丢包")
        else:
            context.evidence.append("ping 失败")

        tracert_result = self._run_action(
            context,
            executor,
            AgentAction(
                action="RUN_TRACERT",
                parameters={"target_ip": scenario["destination_ip"]},
                reason="定位最后可达节点",
            ),
        )
        if not tracert_result.get("success"):
            return self._request_more_data(context, ["tracert_facts"])

        last_reachable = tracert_result["facts"].get("last_reachable_device")
        if last_reachable:
            context.evidence.append(f"tracert 最后可达 {last_reachable}")

        suspect_device = self._resolve_suspect_device(tracert_result)
        if not suspect_device:
            suspect_device = self._resolve_suspect_from_source_route(context, executor)
        if not suspect_device:
            return self._request_more_data(context, ["suspect_device"])

        route_result = self._run_action(
            context,
            executor,
            AgentAction(
                action="CHECK_ROUTE",
                target_device=suspect_device,
                parameters={"destination": scenario["destination_ip"]},
                reason="确认疑似故障设备上的目标路由",
            ),
        )
        baseline_route = context.scenario.get("baseline_route_facts", {}).get(suspect_device, {})
        baseline_available = baseline_route.get("route_found") and baseline_route.get("out_interface")
        route_missing = bool(route_result.get("success")) and route_result["facts"].get("route_found") is False
        if not route_result.get("success"):
            if baseline_available:
                context.evidence.append(f"{suspect_device} 故障前目标路由存在")
                route_result = {"success": True, "facts": baseline_route}
            else:
                return self._request_more_data(context, ["route_facts"])
        elif route_missing:
            context.evidence.append(f"{suspect_device} 目标路由不存在")
            if not baseline_available:
                return self._finish_route_missing(context, suspect_device)
            # An inactive route may be a consequence of a failed outgoing link.
            # The measured baseline identifies an interface, not the expected fault.
            context.evidence.append(f"{suspect_device} 使用故障前目标路由出接口继续核对")
            route_result = {"success": True, "facts": baseline_route}
        else:
            context.evidence.append(f"{suspect_device} 目标路由存在")

        interface_name = self._resolve_interface_name(route_result)
        if not interface_name:
            return self._request_more_data(context, ["interface"])

        interface_result = self._run_action(
            context,
            executor,
            AgentAction(
                action="CHECK_INTERFACE",
                target_device=suspect_device,
                parameters={"interface": interface_name},
                reason="检查目标转发表出接口状态",
            ),
        )
        if not interface_result.get("success"):
            return self._request_more_data(context, ["interface_facts"])
        if interface_result["facts"].get("physical_status") == "DOWN":
            context.evidence.append(
                f"{suspect_device} 出接口 {interface_name} physical_status 为 DOWN"
            )

            return self._finish_diagnosis(
                context,
                {
                    "fault_device": suspect_device,
                    "fault_type": "INTERFACE_DOWN",
                    "fault_interface": interface_name,
                },
            )

        if route_missing:
            facts = interface_result["facts"]
            if facts.get("physical_status") != "UP" or facts.get("protocol_status") != "UP":
                return self._request_more_data(context, ["interface_link_state"])
            context.evidence.append(f"{suspect_device} 故障前出接口 {interface_name} 当前 UP/UP")
            return self._finish_route_missing(context, suspect_device)

        next_hop = route_result["facts"].get("next_hop")
        arp_target = next_hop or scenario["destination_ip"]
        arp_result = self._run_action(
            context,
            executor,
            AgentAction(
                action="CHECK_ARP",
                target_device=suspect_device,
                parameters={"target_ip": arp_target},
                reason="接口正常后继续确认二层可达性",
            ),
        )
        if not arp_result.get("success"):
            return self._request_more_data(context, ["arp_facts"])
        if not arp_result["facts"].get("entry_found"):
            if next_hop and next_hop != scenario["destination_ip"]:
                context.evidence.append(f"{suspect_device} 下一跳 {next_hop} 不可达")
                return self._finish_diagnosis(
                    context,
                    {
                        "fault_device": suspect_device,
                        "fault_type": "NEXT_HOP_UNREACHABLE",
                        "fault_interface": interface_name,
                        "next_hop": next_hop,
                    },
                )
            context.evidence.append(f"{suspect_device} 上 ARP 表项缺失")
            return self._finish_diagnosis(
                context,
                {
                    "fault_device": suspect_device,
                    "fault_type": "ARP_UNRESOLVED",
                    "fault_interface": interface_name,
                    "target_ip": scenario["destination_ip"],
                },
            )

        return self._request_more_data(context, ["deeper_control_plane_checks"])

    def _run_action(self, context: DiagnosisContext, executor: Any, action: AgentAction) -> dict[str, Any]:
        context.actions.append(action.to_dict())
        return executor.execute(action)

    def _resolve_suspect_device(self, tracert_result: dict[str, Any]) -> str | None:
        facts = tracert_result.get("facts", {})
        return facts.get("suspect_device")

    def _resolve_suspect_from_source_route(
        self,
        context: DiagnosisContext,
        executor: Any,
    ) -> str | None:
        """Use the source route's mapped next hop when traceroute is all stars."""
        source_device = context.scenario.get("source_device")
        if not source_device:
            return None
        route_result = self._run_action(
            context,
            executor,
            AgentAction(
                action="CHECK_ROUTE",
                target_device=str(source_device),
                parameters={"destination": context.scenario["destination_ip"]},
                reason="tracert 无可达跳点，检查源设备下一跳",
            ),
        )
        facts = route_result.get("facts", {}) if route_result.get("success") else {}
        next_hop = facts.get("next_hop")
        device = context.scenario.get("ip_to_device", {}).get(next_hop)
        if device:
            context.evidence.append(f"{source_device} 下一跳 {next_hop} 对应 {device}")
            return str(device)
        return None

    def _resolve_interface_name(self, route_result: dict[str, Any]) -> str | None:
        facts = route_result.get("facts", {})
        return facts.get("out_interface")

    def _finish_route_missing(self, context: DiagnosisContext, device: str) -> dict[str, Any]:
        scenario = context.scenario
        return self._finish_diagnosis(context, {
            "fault_device": device,
            "fault_type": "ROUTE_MISSING",
            "fault_interface": None,
            "target_network": scenario.get("destination_network", scenario["destination_ip"]),
        })

    def _finish_normal(self, context: DiagnosisContext) -> dict[str, Any]:
        return {
            "case_id": context.case_id,
            "diagnosis_status": "NORMAL",
            "fault_device": None,
            "fault_type": None,
            "fault_interface": None,
            "required_evidence": context.evidence,
            "action_trace": context.actions,
        }

    def _finish_diagnosis(self, context: DiagnosisContext, diagnosis: dict[str, Any]) -> dict[str, Any]:
        context.actions.append(
            AgentAction(
                action="FINISH_DIAGNOSIS",
                parameters={"diagnosis": diagnosis},
                reason="证据充分，结束诊断",
            ).to_dict()
        )
        result = {
            "case_id": context.case_id,
            "diagnosis_status": "COMPLETED",
            "fault_device": diagnosis["fault_device"],
            "fault_type": diagnosis["fault_type"],
            "fault_interface": diagnosis["fault_interface"],
            "required_evidence": context.evidence,
            "action_trace": context.actions,
        }
        for field in ("target_network", "target_ip", "next_hop"):
            if field in diagnosis:
                result[field] = diagnosis[field]
        return result

    def _request_more_data(self, context: DiagnosisContext, missing_fields: list[str]) -> dict[str, Any]:
        context.actions.append(
            AgentAction(
                action="REQUEST_MORE_DATA",
                parameters={"missing_fields": missing_fields},
                reason="当前证据不足，无法稳定收敛",
            ).to_dict()
        )
        return {
            "case_id": context.case_id,
            "diagnosis_status": "NEED_MORE_DATA",
            "fault_device": None,
            "fault_type": None,
            "fault_interface": None,
            "required_evidence": context.evidence,
            "missing_fields": missing_fields,
            "action_trace": context.actions,
        }
