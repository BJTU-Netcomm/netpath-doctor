from __future__ import annotations

import json

import pytest

from ai.intake_diagnosis import DemoIntakeClient, diagnose_intake


class FakeClient:
    def __init__(self, content: str):
        self.content = content
        self.messages = []

    def chat(self, messages, **kwargs):
        self.messages.append((messages, kwargs))
        return {"choices": [{"message": {"content": self.content}}]}


def test_demo_client_produces_explicit_read_only_connection_result():
    result = diagnose_intake(
        question="浏览器提示连接失败，地址是 192.168.56.101:8090",
        client=DemoIntakeClient(),
    )
    assert result["title"] == "管理服务连接失败"
    assert result["live_checks_performed"] is False
    assert result["next_checks"]
    assert "DEMO" in result["limitations"]


def test_text_diagnosis_normalizes_json_and_does_not_call_live_tools():
    client = FakeClient(json.dumps({
        "title": "接口异常",
        "summary": "发现接口状态异常",
        "observed_facts": ["physical_status=DOWN"],
        "likely_causes": [{"cause": "接口关闭", "reason": "回显显示 DOWN"}],
        "next_checks": ["确认接口配置"],
        "limitations": "没有连接设备",
    }, ensure_ascii=False))
    result = diagnose_intake(question="分析这段 CLI", client=client)
    assert result["observed_facts"] == ["physical_status=DOWN"]
    assert result["likely_causes"][0]["cause"] == "接口关闭"
    assert result["live_checks_performed"] is False
    assert client.messages[0][0][0]["role"] == "system"


def test_image_validation_rejects_unsupported_type_and_oversized_input():
    with pytest.raises(ValueError, match="格式"):
        diagnose_intake(question="看图", image_type="text/plain", image_bytes=b"x")
    with pytest.raises(ValueError, match="5 MB"):
        diagnose_intake(question="看图", image_type="image/png", image_bytes=b"x" * (5 * 1024 * 1024 + 1))


def test_empty_intake_is_rejected():
    with pytest.raises(ValueError, match="输入问题"):
        diagnose_intake(question="")
