from __future__ import annotations

from pathlib import Path

import pytest

from agent.action_schema import AgentAction
from agent.command_mapper import load_action_catalog
from ai.harness import AIHarness
from ai.live_console import LiveConsoleService, ReadOnlyConsole, TracedLiveExecutor
from parser.huawei_vrp import parse_arp
from tests.test_ai_harness import FakeClient, RecordingExecutor, tool_call

ROOT = Path(__file__).resolve().parents[1]


def test_read_only_adapter_blocks_configuration_and_multiline_commands():
    class Transport:
        def send(self, *args):
            raise AssertionError('unsafe command reached transport')
    adapter = ReadOnlyConsole(Transport())
    for command in ['system-view', 'shutdown', 'undo ip route-static 1.1.1.0 255.255.255.0 1.1.1.1',
                    'ping 192.168.3.1\nshutdown', 'display current-configuration']:
        with pytest.raises(ValueError):
            adapter.send('R1', command)


def test_live_executor_rejects_idle_interface_before_contacting_device():
    catalog = load_action_catalog(ROOT / 'rules/action_catalog.json')
    topology = LiveConsoleService(ROOT).topology()
    executor = TracedLiveExecutor({}, catalog, object(), topology, lambda _: None)
    action = AgentAction(action='CHECK_INTERFACE', target_device='R1',
                         parameters={'interface':'GigabitEthernet0/0/2'}, reason='test')
    with pytest.raises(ValueError, match='闲置'):
        executor.execute(action)


def test_normal_result_requires_requested_source_and_target():
    catalog = load_action_catalog(ROOT / 'rules/action_catalog.json')
    client = FakeClient([
        tool_call('run_ping', {'device':'R2', 'target_ip':'10.0.12.1'}),
        tool_call('finish_diagnosis', {'diagnosis':{'diagnosis_status':'NORMAL', 'fault_type':None,
                    'fault_device':None, 'fault_interface':None, 'evidence':['ping reachable']}}),
    ])
    result = AIHarness(client, RecordingExecutor(), catalog).diagnose(
        {'source_device':'R1', 'destination_ip':'192.168.3.1'})
    assert result['diagnosis']['diagnosis_status'] == 'NEED_MORE_DATA'


def test_user_request_is_context_but_experiment_control_is_not_sent():
    catalog = load_action_catalog(ROOT / 'rules/action_catalog.json')
    client = FakeClient([{'choices':[{'message':{'content':'{}'}}]}])
    AIHarness(client, RecordingExecutor(), catalog).diagnose(
        {'source_device':'R1', 'ground_truth':{'fault_type':'secret-answer'},
         'experiment_control':{'inject':'shutdown'}}, question='请检查现在是否正常')
    message = client.calls[0]['messages'][1]['content']
    assert '请检查现在是否正常' in message
    assert 'secret-answer' not in message and 'shutdown' not in message


def test_preflight_closed_console_remains_not_ready(monkeypatch):
    class ClosedConsole:
        def send(self, *args):
            raise ConnectionRefusedError('console closed')
    service = LiveConsoleService(ROOT)
    monkeypatch.setattr(service, 'transport', lambda: ClosedConsole())
    result = service.preflight()
    assert result['ready'] is False and result['writes_performed'] is False
    assert all(not item['ready'] for item in result['devices'])


def test_legacy_vrp_arp_reads_complete_table_and_filters_target_locally():
    table = '''IP ADDRESS      MAC ADDRESS     EXPIRE(M) TYPE        INTERFACE   VPN-INSTANCE
10.0.12.1       00e0-fc6b-0611            I -         GE0/0/0
10.0.12.2       00e0-fc37-2651  19        D-0         GE0/0/0
Total:2         Dynamic:1       Static:0     Interface:1'''
    commands = []
    class Transport:
        last_raw_ref = 'live://arp.txt'
        def send(self, device, command):
            commands.append(command)
            return table
    raw = ReadOnlyConsole(Transport()).send('R1', 'display arp 10.0.12.2')
    assert commands == ['display arp']
    assert parse_arp(raw, {'target_ip':'10.0.12.2'})['entry_found'] is True
    assert parse_arp(raw, {'target_ip':'10.0.12.99'})['entry_found'] is False
    with pytest.raises(ValueError):
        parse_arp(table.split('Total:')[0], {'target_ip':'10.0.12.99'})
