from __future__ import annotations

import socket
import unittest

from tool_server.ensp_console_transport import (
    ENSPConsoleConfigurationError,
    ENSPConsoleTransport,
)


class FakeSocket:
    def __init__(self, replies: list[bytes | None]) -> None:
        self.replies = replies
        self.sent: list[bytes] = []
        self.timeout: float | None = None
        self.closed = False

    def settimeout(self, value: float) -> None:
        self.timeout = value

    def sendall(self, value: bytes) -> None:
        self.sent.append(value)

    def recv(self, _size: int) -> bytes:
        if self.replies:
            reply = self.replies.pop(0)
            if reply is None:
                raise socket.timeout()
            return reply
        raise socket.timeout()

    def close(self) -> None:
        self.closed = True


class ENSPConsoleTransportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.inventory = {
            "R1": {"host": "127.0.0.1", "port": 2000},
            "R2": {"host": "127.0.0.1", "port": 2001},
        }

    def test_command_uses_selected_local_console_and_strips_prompt(self) -> None:
        sock = FakeSocket(
            [
                b"<R2>\r\n",
                b"<R2>\r\n",
                None,
                b"display ip interface brief\r\nGigabitEthernet0/0/0 up up\r\n<R2>\r\n",
            ]
        )
        calls: list[tuple[tuple[str, int], float]] = []

        def factory(address: tuple[str, int], timeout: float) -> FakeSocket:
            calls.append((address, timeout))
            return sock

        transport = ENSPConsoleTransport(
            self.inventory, default_device="R1", socket_factory=factory
        )
        output = transport.send("R2", "display ip interface brief")

        self.assertEqual(calls, [(('127.0.0.1', 2001), 5.0)])
        self.assertEqual(output, "GigabitEthernet0/0/0 up up")
        self.assertEqual(sock.sent, [b"\x1a\r\n", b"display ip interface brief\r\n"])
        self.assertTrue(sock.closed)

    def test_config_commands_enter_and_leave_system_view(self) -> None:
        sock = FakeSocket(
            [
                b"<R2>\r\n",
                b"<R2>\r\n",
                None,
                b"system-view\r\n[R2]\r\n",
                b"interface GigabitEthernet0/0/1\r\n[R2-GigabitEthernet0/0/1]\r\n",
                b"shutdown\r\n[R2-GigabitEthernet0/0/1]\r\n",
                b"return\r\n<R2>\r\n",
            ]
        )
        transport = ENSPConsoleTransport(
            self.inventory, default_device="R1", socket_factory=lambda *_: sock
        )
        output = transport.send_config("R2", ["interface GigabitEthernet0/0/1", "shutdown"])

        self.assertEqual(output, "")
        self.assertEqual(
            sock.sent,
            [
                b"\x1a\r\n",
                b"system-view\r\n",
                b"interface GigabitEthernet0/0/1\r\n",
                b"shutdown\r\n",
                b"return\r\n",
            ],
        )

    def test_command_advances_console_pagination(self) -> None:
        sock = FakeSocket(
            [
                b"<R2>\r\n",
                b"<R2>\r\n",
                None,
                b"display interface GigabitEthernet0/0/1\r\n"
                b"GigabitEthernet0/0/1 current state : UP\r\n"
                b"  ---- More ----",
                b"\r\nLine protocol current state : UP\r\n<R2>\r\n",
            ]
        )
        transport = ENSPConsoleTransport(
            self.inventory, default_device="R1", socket_factory=lambda *_: sock
        )

        output = transport.send("R2", "display interface GigabitEthernet0/0/1")

        self.assertIn("current state : UP", output)
        self.assertIn("Line protocol current state : UP", output)
        self.assertIn(b" ", sock.sent)

    def test_unknown_device_and_invalid_port_are_rejected(self) -> None:
        with self.assertRaisesRegex(ENSPConsoleConfigurationError, "Unknown device"):
            ENSPConsoleTransport(self.inventory, default_device="R1").resolve_device("R3")
        with self.assertRaisesRegex(ENSPConsoleConfigurationError, "valid integer port"):
            ENSPConsoleTransport({"R1": {}}, default_device="R1")

    def test_recovery_requires_interface_up_and_up(self) -> None:
        class RecoveryTransport(ENSPConsoleTransport):
            def __init__(self) -> None:
                super().__init__(self.inventory_for_test(), default_device="R1")
                self.config_attempts = 0

            @staticmethod
            def inventory_for_test() -> dict[str, dict[str, object]]:
                return {
                    "R1": {"host": "127.0.0.1", "port": 2000},
                    "R2": {"host": "127.0.0.1", "port": 2001},
                }

            def _send_config_once(self, device_name: str, commands: list[str]) -> str:
                self.config_attempts += 1
                return ""

            def verify_interface(self, device: str, interface: str) -> dict[str, object]:
                if self.config_attempts < 2:
                    return {
                        "success": False,
                        "physical_status": "DOWN",
                        "protocol_status": "DOWN",
                        "error": "interface still down",
                    }
                return {
                    "success": True,
                    "physical_status": "UP",
                    "protocol_status": "UP",
                    "error": None,
                }

        result = RecoveryTransport().recover_interface(
            "R2", "GigabitEthernet0/0/1", attempts=3
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["attempts"], 2)
        self.assertEqual(result["verification"]["physical_status"], "UP")
        self.assertEqual(result["verification"]["protocol_status"], "UP")


if __name__ == "__main__":
    unittest.main()
