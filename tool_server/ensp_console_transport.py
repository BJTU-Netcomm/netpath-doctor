"""Transport for an eNSP router's local console port.

eNSP exposes each router console on localhost while the topology is running.
This lets the live executor control a locally hosted lab before a separate SSH
management network is available.
"""

from __future__ import annotations

import json
import re
import socket
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any


class ENSPConsoleConfigurationError(ValueError):
    """Raised when a local eNSP console inventory is incomplete."""


SocketFactory = Callable[[tuple[str, int], float], socket.socket]
PROMPT_PATTERN = re.compile(r"(?:<[^<>\r\n]+>|\[[^\[\]\r\n]+\])\s*$")


class ENSPConsoleTransport:
    """Execute VRP commands through eNSP's localhost console ports.

    The eNSP GUI still starts and stops the simulated devices.  This class only
    talks to their running CLI consoles and never starts eNSP or changes the
    Windows network configuration.
    """

    def __init__(
        self,
        devices: Mapping[str, Mapping[str, Any]],
        *,
        default_device: str,
        socket_factory: SocketFactory | None = None,
        connect_timeout: float = 5.0,
        read_timeout: float = 15.0,
        capture_dir: str | Path | None = None,
    ) -> None:
        self.devices = {name: dict(settings) for name, settings in devices.items()}
        self.default_device = default_device
        self._socket_factory = socket_factory or socket.create_connection
        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout
        self.capture_dir = Path(capture_dir) if capture_dir else None
        self._capture_sequence = 0
        self.last_raw_ref: str | None = None
        self._validate_inventory()

    @classmethod
    def from_json(cls, path: str | Path, **kwargs: Any) -> "ENSPConsoleTransport":
        config_path = Path(path)
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ENSPConsoleConfigurationError(
                f"Console config does not exist: {config_path}"
            ) from exc
        except json.JSONDecodeError as exc:
            raise ENSPConsoleConfigurationError(
                f"Console config is not valid JSON: {exc}"
            ) from exc

        devices = config.get("devices")
        default_device = config.get("default_device")
        if not isinstance(devices, dict) or not isinstance(default_device, str):
            raise ENSPConsoleConfigurationError(
                "Console config requires string 'default_device' and object 'devices'"
            )
        return cls(devices, default_device=default_device, **kwargs)

    def resolve_device(self, device: str | None) -> str:
        resolved = device or self.default_device
        if resolved not in self.devices:
            raise ENSPConsoleConfigurationError(f"Unknown device: {resolved}")
        return resolved

    def send(self, device: str | None, command: str | None) -> str:
        if not command or not command.strip():
            raise ValueError("Console command must not be empty")

        device_name = self.resolve_device(device)
        last_error: Exception | None = None
        empty_results = 0
        for _attempt in range(2):
            connection = self._connect(device_name)
            try:
                self._synchronize(connection)
                output = self._send_command(connection, command)
                if output:
                    self._capture(device_name, command, output)
                    return output
                last_error = ValueError("eNSP console returned an empty command result")
                empty_results += 1
            except (TimeoutError, ConnectionError, OSError, ValueError) as exc:
                last_error = exc
            finally:
                connection.close()
        assert last_error is not None
        # Some eNSP/VRP builds return only the prompt when a filtered routing
        # query has no match.  Ask for the complete table so the parser can
        # distinguish a real missing route from a broken/truncated response.
        if empty_results == 2 and re.fullmatch(
            r"display\s+ip\s+routing-table\s+(?:\d{1,3}\.){3}\d{1,3}",
            command.strip(),
            flags=re.IGNORECASE,
        ):
            fallback_command = "display ip routing-table"
            fallback_output = self.send(device_name, fallback_command)
            self._capture(device_name, command + " [fallback]", fallback_output)
            return fallback_output
        raise last_error

    def send_config(self, device: str, commands: list[str]) -> str:
        """Apply experiment-control commands and return the raw VRP output."""
        if not commands or any(not command.strip() for command in commands):
            raise ValueError("Console configuration command list must not be empty")

        device_name = self.resolve_device(device)
        last_error: Exception | None = None
        for _attempt in range(2):
            try:
                output = self._send_config_once(device_name, commands)
                self._capture(device_name, " ; ".join(commands), output)
                return output
            except (TimeoutError, ConnectionError, OSError, ValueError) as exc:
                last_error = exc
        assert last_error is not None
        raise last_error

    def recover_interface(
        self,
        device: str,
        interface: str,
        *,
        attempts: int = 3,
        settle_seconds: float = 1.0,
    ) -> dict[str, Any]:
        """Restore an interface and prove that VRP reports it as up/up.

        eNSP can accept ``undo shutdown`` while returning only a partial
        console response.  A successful write is therefore not enough for a
        live benchmark: each attempt is followed by an independent status
        query, and the result is successful only after both states are UP.
        """
        if attempts < 1:
            raise ValueError("attempts must be at least 1")
        if settle_seconds < 0:
            raise ValueError("settle_seconds must not be negative")
        device_name = self.resolve_device(device)
        commands = [f"interface {interface}", "undo shutdown"]
        errors: list[str] = []
        for attempt in range(1, attempts + 1):
            try:
                output = self._send_config_once(device_name, commands)
                self._capture(device_name, " ; ".join(commands), output)
            except (TimeoutError, ConnectionError, OSError, ValueError) as exc:
                errors.append(f"attempt {attempt}: {type(exc).__name__}: {exc}")
                continue

            if settle_seconds:
                time.sleep(settle_seconds)
            verification = self.verify_interface(device_name, interface)
            if verification["success"]:
                return {
                    "device": device_name,
                    "interface": interface,
                    "commands": commands,
                    "success": True,
                    "attempts": attempt,
                    "verification": verification,
                    "error": None,
                }
            errors.append(
                f"attempt {attempt}: interface verification failed: "
                f"{verification.get('error', 'unknown error')}"
            )

        return {
            "device": device_name,
            "interface": interface,
            "commands": commands,
            "success": False,
            "attempts": attempts,
            "verification": None,
            "error": "; ".join(errors) or "interface recovery failed",
        }

    def verify_interface(self, device: str, interface: str) -> dict[str, Any]:
        """Read one VRP interface and require both physical and protocol UP."""
        from parser.huawei_vrp import parse_cli_output

        try:
            raw_output = self.send(device, f"display interface {interface}")
            parsed = parse_cli_output(
                "CHECK_INTERFACE", raw_output, device=device, context={"interface": interface}
            )
        except Exception as exc:
            return {
                "success": False,
                "physical_status": None,
                "protocol_status": None,
                "error": f"{type(exc).__name__}: {exc}",
            }
        facts = parsed.get("facts", {})
        physical = facts.get("physical_status")
        protocol = facts.get("protocol_status")
        return {
            "success": bool(parsed.get("success")) and physical == "UP" and protocol == "UP",
            "physical_status": physical,
            "protocol_status": protocol,
            "error": parsed.get("error"),
        }

    def _send_config_once(self, device_name: str, commands: list[str]) -> str:
        connection = self._connect(device_name)
        try:
            self._synchronize(connection)
            outputs = [self._send_command(connection, "system-view")]
            for command in commands:
                outputs.append(self._send_command(connection, command))
            outputs.append(self._send_command(connection, "return"))
            return "\n".join(part for part in outputs if part)
        finally:
            connection.close()

    def _validate_inventory(self) -> None:
        if not self.devices:
            raise ENSPConsoleConfigurationError("Console inventory is empty")
        if self.default_device not in self.devices:
            raise ENSPConsoleConfigurationError(
                f"Default device is not present in inventory: {self.default_device}"
            )
        for name, settings in self.devices.items():
            host = settings.get("host", "127.0.0.1")
            if not isinstance(host, str) or not host:
                raise ENSPConsoleConfigurationError(f"Device {name} has invalid host")
            try:
                port = int(settings["port"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ENSPConsoleConfigurationError(
                    f"Device {name} is missing a valid integer port"
                ) from exc
            if not 1 <= port <= 65535:
                raise ENSPConsoleConfigurationError(f"Device {name} has invalid port {port}")

    def _connect(self, device_name: str) -> socket.socket:
        settings = self.devices[device_name]
        host = str(settings.get("host", "127.0.0.1"))
        port = int(settings["port"])
        connection = self._socket_factory((host, port), self.connect_timeout)
        connection.settimeout(self.read_timeout)
        return connection

    def _synchronize(self, connection: socket.socket) -> None:
        """Request a prompt before issuing a command on a fresh console socket."""
        # Ctrl+Z returns VRP to user view if a previous command left the console
        # in system/interface view. It is harmless in user view.
        connection.sendall(b"\x1a\r\n")
        self._read_until_prompt(connection)
        self._drain_initial_prompts(connection)

    def _send_command(self, connection: socket.socket, command: str) -> str:
        connection.sendall((command.strip() + "\r\n").encode("gb18030"))
        raw = self._read_until_prompt(connection)
        return self._strip_echo_and_prompt(raw, command)

    def _drain_initial_prompts(self, connection: socket.socket) -> None:
        """Discard every prompt generated by the synchronization newline."""
        connection.settimeout(0.1)
        try:
            while connection.recv(65535):
                pass
        except socket.timeout:
            return
        finally:
            connection.settimeout(self.read_timeout)

    def _read_until_prompt(self, connection: socket.socket) -> str:
        chunks: list[bytes] = []
        pages_advanced = 0
        while True:
            try:
                chunk = connection.recv(65535)
            except socket.timeout as exc:
                raise TimeoutError("Timed out waiting for an eNSP VRP prompt") from exc
            if not chunk:
                raise ConnectionError("eNSP console closed before returning a VRP prompt")
            chunks.append(chunk)
            text = b"".join(chunks).decode("gb18030", errors="replace")
            normalized = text.replace("\x1b[H", "").replace("\x1b[J", "")
            # Local eNSP consoles use the console line, where the VTY-only
            # ``screen-length 0 temporary`` command is rejected.  Advance
            # every pagination prompt instead of waiting for a final VRP
            # prompt that cannot arrive until the page is acknowledged.
            page_count = normalized.count("---- More ----")
            while pages_advanced < page_count:
                connection.sendall(b" ")
                pages_advanced += 1
            if PROMPT_PATTERN.search(normalized):
                return normalized

    @staticmethod
    def _strip_echo_and_prompt(output: str, command: str) -> str:
        lines = output.replace("\r", "").split("\n")
        while lines and not lines[0].strip():
            lines.pop(0)
        if lines and lines[0].strip() == command.strip():
            lines.pop(0)
        while lines and (not lines[-1].strip() or PROMPT_PATTERN.fullmatch(lines[-1].strip())):
            lines.pop()
        return "\n".join(lines).strip()

    def _capture(self, device: str, command: str, output: str) -> None:
        self.last_raw_ref = None
        if self.capture_dir is None:
            return
        self.capture_dir.mkdir(parents=True, exist_ok=True)
        self._capture_sequence += 1
        command_slug = re.sub(r"[^a-zA-Z0-9]+", "_", command).strip("_").lower()
        filename = f"{self._capture_sequence:02d}_{device}_{command_slug}.txt"
        (self.capture_dir / filename).write_text(output, encoding="utf-8")
        self.last_raw_ref = f"live://{filename}"
