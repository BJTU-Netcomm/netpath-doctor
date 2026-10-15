"""Minimal Bailian (DashScope) OpenAI-compatible client.

The API key is read only from ``DASHSCOPE_API_KEY``.  It must never be stored
in source files, JSON fixtures, reports, or Git.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Mapping, Sequence


DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
# Use the exact model identifier exposed by the Bailian console.  The
# requested Qwen3.8 27B deployment is represented here as qwen3.8-27b;
# override DASHSCOPE_MODEL if the console shows a different identifier.
DEFAULT_MODEL = "qwen3.8-27b"


@dataclass(frozen=True)
class BailianConfig:
    """Runtime configuration for the Bailian OpenAI-compatible endpoint."""

    api_key: str
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    timeout_seconds: float = 120.0

    @classmethod
    def from_env(cls) -> "BailianConfig":
        api_key = os.environ.get("DASHSCOPE_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError(
                "DASHSCOPE_API_KEY is not set; put the key in the local environment, "
                "never in the repository."
            )
        return cls(
            api_key=api_key,
            base_url=os.environ.get("DASHSCOPE_BASE_URL", DEFAULT_BASE_URL).rstrip("/"),
            model=os.environ.get("DASHSCOPE_MODEL", DEFAULT_MODEL),
            timeout_seconds=float(os.environ.get("DASHSCOPE_TIMEOUT_SECONDS", "120")),
        )


class BailianClient:
    """Call Bailian chat completions, including OpenAI-style tool schemas."""

    def __init__(self, config: BailianConfig | None = None) -> None:
        self.config = config or BailianConfig.from_env()

    @property
    def endpoint(self) -> str:
        return f"{self.config.base_url}/chat/completions"

    def chat(
        self,
        messages: Sequence[Mapping[str, Any]],
        *,
        tools: Sequence[Mapping[str, Any]] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 512,
        model: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model or self.config.model,
            "messages": [dict(message) for message in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = [dict(tool) for tool in tools]
            payload["tool_choice"] = "auto"

        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Bailian HTTP {exc.code}: {detail[:1000]}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Bailian connection failed: {exc.reason}") from exc
        except TimeoutError as exc:
            raise RuntimeError(
                f"Bailian request timed out after {self.config.timeout_seconds:g}s"
            ) from exc

        try:
            result = json.loads(body)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Bailian returned non-JSON data") from exc
        if not isinstance(result, dict) or "choices" not in result:
            raise RuntimeError(f"Bailian response has no choices: {body[:1000]}")
        return result


def run_tool_call_smoke_test(client: BailianClient | None = None) -> dict[str, Any]:
    """Ask Qwen to select the project ping tool and return the raw response."""

    client = client or BailianClient()
    tool = {
        "type": "function",
        "function": {
            "name": "run_ping",
            "description": "检查指定设备到目标 IPv4 地址的连通性。",
            "parameters": {
                "type": "object",
                "properties": {
                    "device": {"type": "string"},
                    "target_ip": {"type": "string"},
                },
                "required": ["device", "target_ip"],
            },
        },
    }
    return client.chat(
        [
            {
                "role": "system",
                "content": "你只能通过已注册的网络观察工具获取事实，不能猜测，也不能执行配置命令。",
            },
            {"role": "user", "content": "请检查 R1 到 192.168.3.1 的连通性。"},
        ],
        tools=[tool],
    )
