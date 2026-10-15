from __future__ import annotations

import json
from pathlib import Path

from ai.harness import AIHarness, build_read_only_tools
from agent.action_schema import AgentAction
from agent.command_mapper import load_action_catalog

ROOT = Path(__file__).resolve().parents[1]


class FakeClient:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def chat(self, messages, *, tools=None, **kwargs):
        self.calls.append({"messages": messages, "tools": tools})
        return next(self.responses)


class RecordingExecutor:
    def __init__(self, facts=None):
        self.actions: list[AgentAction] = []
        self.facts = facts or {"reachable": True}

    def execute(self, action):
        self.actions.append(action)
        return {"success": True, "facts": self.facts, "raw_ref": "replay://test/output.txt", "error": None}


def catalog():
    return load_action_catalog(ROOT / "rules" / "action_catalog.json")


def tool_call(name, arguments, call_id="call-1"):
    return {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [{"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(arguments, ensure_ascii=False)}}]}}]}


def test_tool_schemas_expose_only_read_only_observation_actions():
    tools = build_read_only_tools(catalog())
    names = [tool["function"]["name"] for tool in tools]
    assert names == ["run_ping", "run_tracert", "check_route", "check_interface", "check_arp", "finish_diagnosis", "request_more_data"]
    assert all("shutdown" not in json.dumps(tool).lower() for tool in tools)
    assert "device" in tools[0]["function"]["parameters"]["required"]


def test_scenario_answer_fields_are_not_sent_to_model_and_trace_has_provenance():
    client = FakeClient([
        tool_call("run_ping", {"device": "R1", "target_ip": "192.168.3.1"}),
        {"choices": [{"message": {"content": '{"diagnosis_status":"NORMAL","fault_type":null,"fault_device":null,"fault_interface":null,"evidence":["ping reachable"]}'}}]},
    ])
    executor = RecordingExecutor()
    result = AIHarness(client, executor, catalog()).diagnose({"case_id": "TEST", "title": "答案泄漏", "ground_truth": {"fault_type": "secret"}, "destination_ip": "192.168.3.1", "experiment_control": {"command": "shutdown"}})
    assert result["diagnosis"]["diagnosis_status"] == "NORMAL"
    user_message = client.calls[0]["messages"][1]["content"]
    assert "secret" not in user_message and "shutdown" not in user_message and "答案泄漏" not in user_message
    assert result["tool_trace"][0]["arguments"] == {"device": "R1", "target_ip": "192.168.3.1"}
    assert result["tool_trace"][0]["result"]["raw_ref"] == "replay://test/output.txt"


def test_invalid_device_and_newline_never_reach_executor():
    client = FakeClient([
        tool_call("run_ping", {"device": "R2\nshutdown", "target_ip": "192.168.3.1"}),
        {"choices": [{"message": {"content": "{}"}}]},
    ])
    executor = RecordingExecutor()
    result = AIHarness(client, executor, catalog()).diagnose({"destination_ip": "192.168.3.1"})
    assert executor.actions == []
    assert result["tool_trace"][0]["result"]["success"] is False
    assert "device" in result["tool_trace"][0]["result"]["error"]


def test_finish_without_observation_is_rejected_as_need_more_data():
    client = FakeClient([tool_call("finish_diagnosis", {"diagnosis": {"diagnosis_status": "COMPLETED", "fault_type": "INTERFACE_DOWN", "fault_device": "R2", "fault_interface": "GigabitEthernet0/0/1", "evidence": ["I guessed it"]}})])
    result = AIHarness(client, RecordingExecutor(), catalog()).diagnose({"destination_ip": "192.168.3.1"})
    assert result["diagnosis"]["diagnosis_status"] == "NEED_MORE_DATA"
    assert result["tool_trace"][0]["result"]["success"] is False


def test_interface_down_finish_requires_matching_observation():
    client = FakeClient([
        tool_call("check_interface", {"device": "R2", "interface": "GigabitEthernet0/0/1"}),
        tool_call("finish_diagnosis", {"diagnosis": {"diagnosis_status": "COMPLETED", "fault_type": "INTERFACE_DOWN", "fault_device": "R2", "fault_interface": "GigabitEthernet0/0/1", "evidence": ["physical_status=DOWN"]}}, "call-2"),
    ])
    executor = RecordingExecutor({"interface": "GigabitEthernet0/0/1", "physical_status": "DOWN", "protocol_status": "DOWN"})
    result = AIHarness(client, executor, catalog()).diagnose({"destination_ip": "192.168.3.1"})
    assert result["diagnosis"]["fault_type"] == "INTERFACE_DOWN"
    assert result["tool_trace"][-1]["result"]["success"] is True


def test_capability_summary_is_added_without_answer_fields():
    class CapabilityExecutor(RecordingExecutor):
        def capability_summary(self):
            return {"available_observations": [{"action": "RUN_PING", "device": "R1"}], "note": "safe"}

    client = FakeClient([{"choices": [{"message": {"content": "{}"}}]}])
    AIHarness(client, CapabilityExecutor(), catalog()).diagnose({"title": "hidden", "ground_truth": {"fault_type": "secret"}})
    user_message = client.calls[0]["messages"][1]["content"]
    assert "available_observations" in user_message
    assert "secret" not in user_message and "hidden" not in user_message


def test_long_evidence_is_rejected_by_local_contract():
    evidence = ["x" * 121]
    client = FakeClient([tool_call("finish_diagnosis", {"diagnosis": {"diagnosis_status": "NORMAL", "fault_type": None, "fault_device": None, "fault_interface": None, "evidence": evidence}})])
    result = AIHarness(client, RecordingExecutor(), catalog()).diagnose({"destination_ip": "192.168.3.1"})
    assert result["diagnosis"]["diagnosis_status"] == "NEED_MORE_DATA"


def test_truncated_terminal_json_can_be_retried():
    client = FakeClient([
        tool_call("run_ping", {"device": "R1", "target_ip": "192.168.3.1"}),
        tool_call("finish_diagnosis", {"diagnosis": {"diagnosis_status": "NORMAL", "fault_type": None, "fault_device": None, "fault_interface": None, "evidence": ["reachable"]}}, "call-2"),
    ])
    # Replace the second response with a deliberately truncated JSON string.
    client.responses = iter([
        tool_call("run_ping", {"device": "R1", "target_ip": "192.168.3.1"}),
        {"choices": [{"message": {"content": None, "tool_calls": [{"id": "call-2", "type": "function", "function": {"name": "finish_diagnosis", "arguments": '{"diagnosis":{"diagnosis_status":"NORMAL"}'}}]}}]},
        tool_call("finish_diagnosis", {"diagnosis": {"diagnosis_status": "NORMAL", "fault_type": None, "fault_device": None, "fault_interface": None, "evidence": ["reachable"]}}, "call-3"),
    ])
    result = AIHarness(client, RecordingExecutor({"reachable": True}), catalog()).diagnose({"destination_ip": "192.168.3.1"})
    assert result["diagnosis"]["diagnosis_status"] == "NORMAL"
    assert result["tool_trace"][1]["result"]["success"] is False
    assert result["tool_trace"][2]["result"]["success"] is True
