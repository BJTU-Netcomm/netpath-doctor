"""Exercise browser -> console -> HTTP model provider without external services."""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from pathlib import Path
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from ai.bailian_client import BailianClient
from ai.console_config import ConsoleConfig
from ai.live_console import LiveConsoleService
from tools import diagnosis_server


@pytest.fixture
def console(tmp_path, monkeypatch):
    for name in list(__import__('os').environ):
        if name.startswith(('DASHSCOPE_', 'NETPATH_UI_')):
            monkeypatch.delenv(name)
    calls = []
    control = {'failure': False}

    class Provider(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            calls.append({'path': self.path, 'body': body, 'auth': self.headers.get('Authorization')})
            if control['failure']:
                self.send_response(401)
                self.end_headers()
                self.wfile.write(b'credential rejected: test-secret')
                return
            content = 'OK' if body['max_tokens'] == 32 else json.dumps({
                'title': '接口检查建议', 'summary': '输入显示接口 DOWN，需核查配置。',
                'observed_facts': ['physical_status=DOWN'],
                'likely_causes': [{'cause': '接口异常', 'reason': '用户提供回显'}],
                'next_checks': ['检查接口配置'], 'limitations': '未连接设备',
            })
            message = {'content': content}
            if body.get('tools'):
                tool_messages = [item for item in body['messages'] if item['role'] == 'tool']
                if not tool_messages:
                    name, arguments = 'run_ping', {'device': 'R1', 'target_ip': '192.168.3.1'}
                else:
                    name, arguments = 'finish_diagnosis', {'diagnosis': {
                        'diagnosis_status': 'NORMAL', 'fault_type': None, 'fault_device': None,
                        'fault_interface': None, 'evidence': ['目标 ping 可达']}}
                message = {'content': None, 'tool_calls': [{'id': f'call-{len(tool_messages)}', 'type': 'function',
                            'function': {'name': name, 'arguments': json.dumps(arguments)}}]}
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps({'choices': [{'message': message}]}).encode())

    provider = ThreadingHTTPServer(('127.0.0.1', 0), Provider)
    provider_thread = threading.Thread(target=provider.serve_forever, daemon=True)
    provider_thread.start()
    # Keep production HTTPS validation; route only the test client to the local fixture.
    def client(config):
        return BailianClient(replace(config, base_url=f'http://127.0.0.1:{provider.server_port}/v1'))

    monkeypatch.setattr(diagnosis_server, 'BailianClient', client)
    settings = ConsoleConfig(tmp_path)
    server = diagnosis_server.DiagnosisServer(('127.0.0.1', 0), settings)
    project = Path(__file__).resolve().parents[1]
    (tmp_path / 'config').mkdir(exist_ok=True)
    (tmp_path / 'rules').mkdir(exist_ok=True)
    (tmp_path / 'config' / 'diagnosis_topology.json').write_bytes((project / 'config' / 'diagnosis_topology.json').read_bytes())
    (tmp_path / 'rules' / 'action_catalog.json').write_bytes((project / 'rules' / 'action_catalog.json').read_bytes())
    class FakeConsole:
        last_raw_ref = 'live://test/ping.txt'
        def send(self, device, command):
            if command == 'display ip interface brief':
                return 'Interface IP Address/Mask Physical Protocol\nGE0/0/0 10.0.12.1/24 up up'
            return (project / 'scenarios/golden/case_004_normal/ping.txt').read_text(encoding='utf-8')
    service = LiveConsoleService(tmp_path)
    service.transport = lambda capture_dir=None: FakeConsole()
    server.live = service
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f'http://127.0.0.1:{server.server_port}'

    def request(path, data=None, origin=None):
        headers = {'Content-Type': 'application/json'}
        if origin:
            headers['Origin'] = origin
        req = urllib.request.Request(url + path, data=None if data is None else json.dumps(data).encode(), headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                return response.status, response.read().decode()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode()

    yield request, calls, control, settings
    server.shutdown()
    provider.shutdown()
    server.server_close()
    provider.server_close()
    thread.join(timeout=2)
    provider_thread.join(timeout=2)


def configure(request, **extra):
    code, text = request('/api/config', {'api_key': 'test-secret', 'model': 'test-qwen',
                                        'base_url': 'https://example.invalid/v1', **extra})
    assert code == 200
    assert 'test-secret' not in text


def test_text_api_uses_real_http_client_and_streams_result(console):
    request, calls, _, _ = console
    configure(request)
    code, text = request('/api/diagnose', {'question': 'R2 physical_status=DOWN', 'stream': True})
    events = [json.loads(line) for line in text.splitlines()]
    assert code == 200
    assert events[0]['event'] == 'progress'
    assert events[-1]['event'] == 'result'
    assert events[-1]['result']['execution_mode'] == 'api'
    assert events[-1]['result']['model'] == 'test-qwen'
    assert events[-1]['result']['live_checks_performed'] is False
    assert calls[0]['auth'] == 'Bearer test-secret'
    assert calls[0]['path'] == '/v1/chat/completions'
    assert 'test-secret' not in text


def test_api_probe_and_public_status_do_not_leak_credentials(console):
    request, calls, _, _ = console
    configure(request)
    code, _ = request('/api/check-provider', {})
    assert code == 200
    code, text = request('/api/health')
    assert json.loads(text)['provider_verified'] is True
    assert 'test-secret' not in text and 'api_key' not in text
    assert calls[0]['body']['max_tokens'] == 32


def test_image_selects_vision_model_and_sends_data_uri(console):
    request, calls, _, _ = console
    configure(request, vision_model='test-vision')
    code, text = request('/api/diagnose', {'question': '看图', 'image_data': 'data:image/png;base64,iVBORw0KGgo='})
    assert code == 200
    assert json.loads(text)['result']['model'] == 'test-vision'
    payload = calls[0]['body']
    assert payload['model'] == 'test-vision'
    assert payload['messages'][1]['content'][1]['type'] == 'image_url'


def test_provider_auth_failure_is_reported_without_demo_fallback(console):
    request, _, control, _ = console
    configure(request)
    control['failure'] = True
    _, text = request('/api/diagnose', {'question': '检查故障', 'stream': True})
    events = [json.loads(line) for line in text.splitlines()]
    assert events[-1]['event'] == 'error'
    assert '认证失败' in events[-1]['error']
    assert 'test-secret' not in text
    assert not any(event['event'] == 'result' for event in events)


def test_missing_key_returns_actionable_error(console):
    request, calls, _, _ = console
    code, text = request('/api/diagnose', {'question': '检查网络'})
    assert code == 400 and 'API 设置' in text
    assert calls == []


def test_settings_persist_only_when_selected_and_blank_key_preserves_secret(console):
    request, _, _, settings = console
    configure(request)
    assert not settings.path.exists()
    configure(request, persist=True)
    assert json.loads(settings.path.read_text())['api_key'] == 'test-secret'
    request('/api/config', {'api_key': '', 'model': 'changed-model'})
    assert settings.client_config()[0].api_key == 'test-secret'


def test_demo_remains_explicit_and_external_origins_are_rejected(console):
    request, calls, _, _ = console
    request('/api/config', {'mode': 'demo'})
    code, text = request('/api/diagnose', {'question': '连接失败'})
    assert code == 200
    assert json.loads(text)['result']['execution_mode'] == 'demo'
    assert calls == []
    code, _ = request('/api/config', {'mode': 'api'}, origin='https://other.invalid')
    assert code == 403


def test_malformed_input_never_reaches_provider_and_static_paths_are_closed(console):
    request, calls, _, _ = console
    configure(request)
    code, _ = request('/api/diagnose', {'question': '看图', 'image_data': 'not-an-image'})
    assert code == 400 and not calls
    code, _ = request('/assets/../../config/diagnosis_ui.local.json')
    assert code == 404


def test_web_live_diagnosis_streams_tools_and_saves_report(console):
    request, calls, _, settings = console
    configure(request)
    code, text = request('/api/diagnose', {'diagnosis_kind':'live', 'source_device':'R1',
                                          'target_ip':'192.168.3.1', 'question':'检查当前连通性', 'stream':True})
    assert code == 200
    events = [json.loads(line) for line in text.splitlines()]
    assert any(event['event'] == 'tool_start' and event['command'] == 'ping 192.168.3.1' for event in events)
    assert any(event['event'] == 'tool_result' and event['raw_output'] for event in events)
    result = events[-1]['result']
    assert result['diagnosis']['diagnosis_status'] == 'NORMAL'
    assert result['writes_performed'] is False
    assert result['execution_mode'] == 'ai_live_console'
    assert len(calls) == 2 and 'tools' in calls[0]['body']
    report = settings.path.parents[1] / 'reports' / 'ui_live' / result['run_id'] / 'report.json'
    assert report.exists() and 'test-secret' not in report.read_text(encoding='utf-8')


def test_web_preflight_reads_console_without_model_and_live_rejects_demo(console):
    request, calls, _, _ = console
    code, text = request('/api/ensp/preflight', {})
    assert code == 200 and json.loads(text)['ready'] is True
    assert len(json.loads(text)['devices']) == 3 and calls == []
    request('/api/config', {'mode':'demo'})
    code, text = request('/api/diagnose', {'diagnosis_kind':'live'})
    assert code == 400 and '真实 API' in text and calls == []


def test_invalid_live_target_never_reaches_model(console):
    request, calls, _, _ = console
    configure(request)
    code, _ = request('/api/diagnose', {'diagnosis_kind':'live', 'target_ip':'1.2.3.4\nshutdown'})
    assert code == 400 and calls == []
