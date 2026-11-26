"""Local-only configuration for the browser console. Public views omit secrets."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from urllib.parse import urlsplit

from ai.bailian_client import BailianConfig, DEFAULT_BASE_URL, DEFAULT_MODEL


class ConsoleConfig:
    def __init__(self, root: Path):
        self.path = root / "config" / "diagnosis_ui.local.json"
        self.lock = threading.Lock()
        values = dict(os.environ)
        for path in (root / "config" / "bailian.local.env", root / ".env"):
            if path.exists():
                for line in path.read_text(encoding="utf-8-sig").splitlines():
                    name, sep, value = line.strip().partition("=")
                    if sep and name.startswith("DASHSCOPE_"):
                        values.setdefault(name, value.strip().strip('"').strip("'"))
        self.values = {
            "api_key": values.get("DASHSCOPE_API_KEY", ""),
            "base_url": values.get("DASHSCOPE_BASE_URL", DEFAULT_BASE_URL),
            "model": values.get("DASHSCOPE_MODEL", DEFAULT_MODEL),
            "vision_model": values.get("DASHSCOPE_VISION_MODEL", ""),
            "timeout_seconds": values.get("DASHSCOPE_TIMEOUT_SECONDS", "120"),
            "mode": "demo" if values.get("NETPATH_UI_DEMO", "0").lower() in {"1", "true", "yes"} else "api",
        }
        if self.path.exists():
            saved = json.loads(self.path.read_text(encoding="utf-8"))
            self.values.update({k: v for k, v in saved.items() if k in self.values})
        self.verified = False

    def public(self) -> dict:
        with self.lock:
            return {**{k: v for k, v in self.values.items() if k != "api_key"},
                    "provider_configured": bool(self.values["api_key"]),
                    "provider_verified": self.verified}

    def update(self, data: dict) -> None:
        with self.lock:
            proposed = dict(self.values)
            for key in ("base_url", "model", "vision_model", "mode", "api_key"):
                if key in data:
                    if not isinstance(data[key], str) or any(ord(c) < 32 for c in data[key]):
                        raise ValueError("配置字段必须为单行文本。")
                    value = data[key].strip()
                    if key != "api_key" or value:
                        proposed[key] = value
            endpoint = urlsplit(proposed["base_url"])
            if endpoint.scheme != "https" or not endpoint.hostname or endpoint.username or endpoint.password or endpoint.query or endpoint.fragment:
                raise ValueError("Base URL 必须是完整的 HTTPS 地址，不含账号、查询参数或片段。")
            proposed["base_url"] = proposed["base_url"].rstrip("/")
            if not proposed["model"]:
                raise ValueError("请输入百炼部署中实际存在的模型 ID。")
            if proposed["mode"] not in {"api", "demo"}:
                raise ValueError("模式必须为 api 或 demo。")
            if data.get("persist") is True:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                temporary = self.path.with_suffix(".tmp")
                temporary.write_text(json.dumps(proposed, ensure_ascii=False, indent=2), encoding="utf-8")
                temporary.replace(self.path)
            self.values = proposed
            self.verified = False

    def client_config(self) -> tuple[BailianConfig, str]:
        with self.lock:
            values = dict(self.values)
        if not values["api_key"]:
            raise ValueError("尚未配置 API Key，请打开右上角“API 设置”填写。")
        try:
            timeout = float(values["timeout_seconds"])
        except (ValueError, TypeError) as exc:
            raise ValueError("DASHSCOPE_TIMEOUT_SECONDS 必须为数字。") from exc
        if not 1 <= timeout <= 300:
            raise ValueError("API 超时时间必须在 1～300 秒之间。")
        return BailianConfig(api_key=values["api_key"], base_url=values["base_url"].rstrip("/"),
                             model=values["model"], timeout_seconds=timeout), values["vision_model"]

    def error_message(self, exc: Exception) -> str:
        message = str(exc)
        with self.lock:
            key = self.values["api_key"]
        if key:
            message = message.replace(key, "[redacted]")
        if "401" in message or "403" in message:
            return "百炼认证失败或权限不足，请检查 API Key 与工作空间地址是否匹配。"
        if "404" in message:
            return "百炼接口或模型不存在，请检查兼容模式 Base URL 和实际模型 ID。"
        if "429" in message:
            return "API 请求受到限流或额度限制，请检查百炼控制台后重试。"
        if "timed out" in message.lower():
            return "等待模型响应超时，请稍后重试或调整本地超时时间。"
        return message[:1200]
