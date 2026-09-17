from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tool_server.ssh_transport import SSHConfigurationError, SSHTransport


class FakeConnection:
    def __init__(self, output: str) -> None:
        self.output = output
        self.calls: list[tuple[str, float, bool, bool]] = []
        self.disconnected = False

    def send_command(
        self,
        command: str,
        *,
        read_timeout: float,
        strip_prompt: bool,
        strip_command: bool,
    ) -> str:
        self.calls.append((command, read_timeout, strip_prompt, strip_command))
        return self.output

    def disconnect(self) -> None:
        self.disconnected = True


class SSHTransportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.inventory = {
            "R1": {
                "host": "192.0.2.1",
                "username": "tester",
                "password_env": "TEST_R1_PASSWORD",
            },
            "R2": {
                "host": "192.0.2.2",
                "username": "tester",
                "password_env": "TEST_R2_PASSWORD",
            },
        }

    def test_default_device_executes_command_and_disconnects(self) -> None:
        fake_connection = FakeConnection("5 packet(s) received\n0.00% packet loss")
        connect_calls: list[dict] = []

        def connector(**kwargs):
            connect_calls.append(kwargs)
            return fake_connection

        transport = SSHTransport(
            self.inventory,
            default_device="R1",
            connector=connector,
            environ={"TEST_R1_PASSWORD": "secret"},
        )
        output = transport.send(None, "ping 192.0.2.10")

        self.assertIn("0.00% packet loss", output)
        self.assertEqual(connect_calls[0]["host"], "192.0.2.1")
        self.assertEqual(connect_calls[0]["password"], "secret")
        self.assertEqual(fake_connection.calls[0][0], "ping 192.0.2.10")
        self.assertTrue(fake_connection.disconnected)

    def test_named_device_selects_matching_connection(self) -> None:
        connect_calls: list[dict] = []

        def connector(**kwargs):
            connect_calls.append(kwargs)
            return FakeConnection("interface output")

        transport = SSHTransport(
            self.inventory,
            default_device="R1",
            connector=connector,
            environ={"TEST_R2_PASSWORD": "r2-secret"},
        )
        transport.send("R2", "display interface GigabitEthernet0/0/1")

        self.assertEqual(connect_calls[0]["host"], "192.0.2.2")
        self.assertEqual(connect_calls[0]["password"], "r2-secret")

    def test_plaintext_password_is_rejected(self) -> None:
        inventory = {
            "R1": {
                "host": "192.0.2.1",
                "username": "tester",
                "password": "unsafe",
                "password_env": "TEST_R1_PASSWORD",
            }
        }
        with self.assertRaisesRegex(SSHConfigurationError, "plaintext"):
            SSHTransport(inventory, default_device="R1")

    def test_missing_password_environment_variable_is_clear(self) -> None:
        transport = SSHTransport(
            self.inventory,
            default_device="R1",
            connector=lambda **_: FakeConnection("unused"),
            environ={},
        )
        with self.assertRaisesRegex(SSHConfigurationError, "TEST_R1_PASSWORD"):
            transport.send("R1", "display arp")

    def test_from_json_and_raw_output_capture(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "devices.json"
            config_path.write_text(
                json.dumps(
                    {"default_device": "R1", "devices": {"R1": self.inventory["R1"]}}
                ),
                encoding="utf-8",
            )
            transport = SSHTransport.from_json(
                config_path,
                connector=lambda **_: FakeConnection("raw cli output"),
                environ={"TEST_R1_PASSWORD": "secret"},
                capture_dir=root / "raw",
            )

            transport.send(None, "display ip routing-table 192.0.2.10")

            captures = list((root / "raw").glob("*.txt"))
            self.assertEqual(len(captures), 1)
            self.assertEqual(captures[0].read_text(encoding="utf-8"), "raw cli output")


if __name__ == "__main__":
    unittest.main()
