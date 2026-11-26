from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from ai.live_console import LiveConsoleService
from ai.console_config import ConsoleConfig
from tools.diagnosis_server import DiagnosisServer


class FakeFaultTransport:
    def __init__(self) -> None:
        self.interface_up = True
        self.route_present = True
        self.config_calls: list[tuple[str, list[str]]] = []
        self.fail_after_config_change = False

    def send(self, device: str, command: str) -> str:
        if command.startswith("ping "):
            if self.interface_up and self.route_present:
                return "5 packet(s) transmitted\n5 packet(s) received\n0.00% packet loss"
            return "5 packet(s) transmitted\n0 packet(s) received\n100.00% packet loss"
        if command.startswith("display ip routing-table"):
            if not self.route_present:
                return "Route Flags: R - relay\nRoute Count : 0"
            return (
                "Route Flags: R - relay, D - download to fib\n"
                "Summary Count : 1\n"
                "192.168.3.0/24 Static 60 0 RD 10.0.23.2 GigabitEthernet0/0/1"
            )
        if command.startswith("display interface"):
            state = "UP" if self.interface_up else "DOWN"
            return (f"GigabitEthernet0/0/1 current state : {state}\n"
                    f"Line protocol current state : {state}")
        raise AssertionError(f"Unexpected command: {command}")

    def send_config(self, device: str, commands: list[str]) -> str:
        self.config_calls.append((device, commands))
        last = commands[-1]
        if last == "shutdown":
            self.interface_up = False
        elif last == "undo shutdown":
            self.interface_up = True
        elif last.startswith("undo ip route-static"):
            self.route_present = False
        elif last.startswith("ip route-static"):
            self.route_present = True
        else:
            raise AssertionError(f"Unexpected configuration: {commands}")
        if self.fail_after_config_change:
            self.fail_after_config_change = False
            raise TimeoutError("simulated response loss")
        return ""


@pytest.fixture
def service(tmp_path: Path) -> tuple[LiveConsoleService, FakeFaultTransport]:
    project = Path(__file__).resolve().parents[1]
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "diagnosis_topology.json").write_bytes(
        (project / "config" / "diagnosis_topology.json").read_bytes()
    )
    transport = FakeFaultTransport()
    control = LiveConsoleService(tmp_path)
    control.transport = lambda capture_dir=None: transport
    return control, transport


def test_interface_fault_is_verified_and_can_be_restored(service) -> None:
    control, transport = service

    injected = control.inject_fault("INTERFACE_DOWN")

    assert injected["active"] is True
    assert injected["verification"]["facts"]["physical_status"] == "DOWN"
    assert transport.interface_up is False

    recovered = control.recover_fault("INTERFACE_DOWN")

    assert recovered["active"] is False
    assert recovered["verification"]["facts"]["physical_status"] == "UP"
    assert transport.interface_up is True


def test_route_fault_is_verified_and_can_be_restored(service) -> None:
    control, transport = service

    injected = control.inject_fault("ROUTE_MISSING")

    assert injected["active"] is True
    assert injected["verification"]["facts"]["route_found"] is False
    assert transport.route_present is False

    recovered = control.recover_fault("ROUTE_MISSING")

    assert recovered["active"] is False
    assert recovered["verification"]["facts"]["route_found"] is True
    assert transport.route_present is True


def test_unavailable_baseline_does_not_write_configuration(service) -> None:
    control, transport = service
    transport.route_present = False

    with pytest.raises(ValueError, match="基线连通性"):
        control.inject_fault("INTERFACE_DOWN")

    assert transport.config_calls == []


def test_unknown_fault_type_is_rejected(service) -> None:
    control, transport = service

    with pytest.raises(ValueError, match="支持的故障类型"):
        control.inject_fault("任意命令")

    assert transport.config_calls == []


def test_uncertain_injection_attempt_is_rolled_back_and_verified(service) -> None:
    control, transport = service
    transport.fail_after_config_change = True

    with pytest.raises(RuntimeError, match="已确认恢复"):
        control.inject_fault("INTERFACE_DOWN")

    assert transport.interface_up is True
    assert [commands[-1] for _, commands in transport.config_calls] == ["shutdown", "undo shutdown"]


def test_fault_api_tracks_injection_and_recovery(tmp_path: Path) -> None:
    server = DiagnosisServer(("127.0.0.1", 0), ConsoleConfig(tmp_path))
    calls = []

    class StubControl:
        def inject_fault(self, fault_type):
            calls.append(("inject", fault_type))
            return {"fault_type": fault_type, "active": True, "message": "injected"}

        def recover_fault(self, fault_type):
            calls.append(("recover", fault_type))
            return {"fault_type": fault_type, "active": False, "message": "recovered"}

    server.live = StubControl()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}"

    def post(path: str, data: dict):
        request = urllib.request.Request(
            url + path,
            data=json.dumps(data).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=3) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    try:
        status, injected = post("/api/fault", {"action": "inject", "fault_type": "ROUTE_MISSING"})
        assert status == 200
        assert injected["active_fault"] == "ROUTE_MISSING"

        status, duplicate = post("/api/fault", {"action": "inject", "fault_type": "INTERFACE_DOWN"})
        assert status == 400
        assert "已有" in duplicate["error"]

        status, recovered = post("/api/fault", {"action": "recover", "fault_type": "ROUTE_MISSING"})
        assert status == 200
        assert recovered["active_fault"] is None
        assert calls == [("inject", "ROUTE_MISSING"), ("recover", "ROUTE_MISSING")]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
