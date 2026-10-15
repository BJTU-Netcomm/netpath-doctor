from __future__ import annotations

import json
import os
import re
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any


class SSHConfigurationError(ValueError):
    """Raised when the local device configuration is incomplete or unsafe."""


class SSHTransport:
    """Execute one VRP command over SSH using a named device inventory."""

    def __init__(
        self,
        devices: Mapping[str, Mapping[str, Any]],
        *,
        default_device: str,
        connector: Callable[..., Any] | None = None,
        environ: Mapping[str, str] | None = None,
        command_timeout: float = 30.0,
        capture_dir: str | Path | None = None,
    ) -> None:
        self.devices = {name: dict(settings) for name, settings in devices.items()}
        self.default_device = default_device
        self._connector = connector
        self._environ = environ if environ is not None else os.environ
        self.command_timeout = command_timeout
        self.capture_dir = Path(capture_dir) if capture_dir else None
        self._capture_sequence = 0
        self.last_raw_ref: str | None = None
        self._validate_inventory()

    @classmethod
    def from_json(
        cls,
        path: str | Path,
        **kwargs: Any,
    ) -> "SSHTransport":
        config_path = Path(path)
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise SSHConfigurationError(f"Device config does not exist: {config_path}") from exc
        except json.JSONDecodeError as exc:
            raise SSHConfigurationError(f"Device config is not valid JSON: {exc}") from exc

        devices = config.get("devices")
        default_device = config.get("default_device")
        if not isinstance(devices, dict) or not isinstance(default_device, str):
            raise SSHConfigurationError(
                "Device config requires string 'default_device' and object 'devices'"
            )
        return cls(devices, default_device=default_device, **kwargs)

    def resolve_device(self, device: str | None) -> str:
        resolved = device or self.default_device
        if resolved not in self.devices:
            raise SSHConfigurationError(f"Unknown device: {resolved}")
        return resolved

    def send(self, device: str | None, command: str | None) -> str:
        if not command or not command.strip():
            raise ValueError("SSH command must not be empty")

        device_name = self.resolve_device(device)
        connection = self._connect(device_name)
        try:
            output = connection.send_command(
                command,
                read_timeout=self.command_timeout,
                strip_prompt=True,
                strip_command=True,
            )
        finally:
            connection.disconnect()

        if not isinstance(output, str):
            raise TypeError("SSH client returned a non-text command result")
        self._capture(device_name, command, output)
        return output

    def send_config(self, device: str, commands: list[str]) -> str:
        """Send experiment-control commands outside the read-only Agent path."""
        if not commands or any(not command.strip() for command in commands):
            raise ValueError("SSH configuration command list must not be empty")

        device_name = self.resolve_device(device)
        connection = self._connect(device_name)
        try:
            output = connection.send_config_set(
                commands,
                read_timeout=self.command_timeout,
                strip_prompt=False,
                strip_command=False,
            )
        finally:
            connection.disconnect()

        if not isinstance(output, str):
            raise TypeError("SSH client returned a non-text configuration result")
        self._capture(device_name, " ; ".join(commands), output)
        return output

    def _validate_inventory(self) -> None:
        if not self.devices:
            raise SSHConfigurationError("Device inventory is empty")
        if self.default_device not in self.devices:
            raise SSHConfigurationError(
                f"Default device is not present in inventory: {self.default_device}"
            )

        for name, settings in self.devices.items():
            if "password" in settings:
                raise SSHConfigurationError(
                    f"Device {name} contains plaintext 'password'; use 'password_env'"
                )
            missing = [
                field
                for field in ("host", "username", "password_env")
                if not settings.get(field)
            ]
            if missing:
                raise SSHConfigurationError(
                    f"Device {name} is missing required fields: {', '.join(missing)}"
                )

    def _connect(self, device_name: str) -> Any:
        settings = self.devices[device_name]
        password_env = str(settings["password_env"])
        password = self._environ.get(password_env)
        if not password:
            raise SSHConfigurationError(
                f"Environment variable {password_env} is not set for device {device_name}"
            )

        connector = self._connector
        if connector is None:
            try:
                from netmiko import ConnectHandler
            except ImportError as exc:
                raise RuntimeError(
                    "Netmiko is not installed; run 'uv pip install -r requirements.txt'"
                ) from exc
            connector = ConnectHandler

        return connector(
            device_type=settings.get("device_type", "huawei"),
            host=str(settings["host"]),
            port=int(settings.get("port", 22)),
            username=str(settings["username"]),
            password=password,
            conn_timeout=float(settings.get("connect_timeout", 10)),
            auth_timeout=float(settings.get("auth_timeout", 10)),
            banner_timeout=float(settings.get("banner_timeout", 15)),
            fast_cli=False,
        )

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
