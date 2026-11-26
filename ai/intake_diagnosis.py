"""Text and screenshot intake for an initial, non-invasive diagnosis."""

from __future__ import annotations

import base64
import json
import os
import re
from typing import Any, Callable

from ai.bailian_client import BailianClient

MAX_TEXT_LENGTH = 8000
MAX_IMAGE_BYTES = 5 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp"}

_SYSTEM_PROMPT = """你是 NetPath-Doctor 的网络故障初步分析助手。用户会提交问题文字、网络设备输出或截图。
先忠实提取输入中可直接观察到的事实，再给出有依据的可能原因和可执行的下一步检查。
严格区分“截图/文字明确显示的事实”和“待验证的推测”。没有连接设备工具，不要声称执行过 ping、SSH、路由查询或任何实时检测；不能把建议写成已完成操作。若信息不足，明确指出缺少什么。
使用简体中文，表达简洁易懂。只返回一个 JSON 对象，不要 Markdown 代码围栏，字段为：
{"title":"简短标题","summary":"结论摘要","observed_facts":["直接观察到的事实"],"likely_causes":[{"cause":"可能原因","reason":"依据或说明"}],"next_checks":["按顺序可执行的检查步骤"],"limitations":"本次分析的边界或缺失信息"}
不要要求用户公开密码、API Key 或其他凭据。"""


class DemoIntakeClient:
    """Deterministic local response for a presentation without network access.

    The UI labels this mode as DEMO. It is deliberately separate from the
    Bailian client so a demonstration cannot be mistaken for a model result.
    """

    def chat(self, messages: Any, **_: Any) -> dict[str, Any]:
        user_message = messages[-1].get("content", "") if messages else ""
        if isinstance(user_message, list):
            user_message = " ".join(
                part.get("text", "") for part in user_message if isinstance(part, dict)
            )
        text = str(user_message)
        if any(word in text.lower() for word in ("连接失败", "connection refused", "8090", "无法建立")):
            payload = {
                "title": "管理服务连接失败",
                "summary": "输入显示浏览器无法连接 192.168.56.101:8090；当前只能确认服务端口没有建立成功连接，具体原因仍需现场检查。",
                "observed_facts": [
                    "页面显示“连接失败”",
                    "目标地址为 192.168.56.101:8090",
                    "浏览器提示暂时无法建立与服务器的连接",
                ],
                "likely_causes": [
                    {"cause": "目标服务未启动或监听端口不一致", "reason": "连接被拒绝/无法建立时，首先核对服务进程和端口。"},
                    {"cause": "虚拟网卡或本机网络路径异常", "reason": "192.168.56.0/24 常用于本机虚拟网络，需要检查网卡和地址。"},
                    {"cause": "防火墙或安全软件拦截", "reason": "系统安全策略可能阻断本地端口访问。"},
                ],
                "next_checks": [
                    "确认目标程序已启动，并核对它实际监听的 IP 与端口",
                    "在 PowerShell 执行 Test-NetConnection 192.168.56.101 -Port 8090",
                    "检查 VirtualBox Host-Only Network 的地址和启用状态",
                    "记录检查结果后再进行 eNSP 节点启动测试",
                ],
                "limitations": "这是本地 DEMO 模式的结构化示例，没有连接 eNSP、没有执行端口探测，也没有修改设备配置。",
            }
        else:
            payload = {
                "title": "需要补充现场证据",
                "summary": "已收到问题，但目前无法从输入中确认具体故障类型。",
                "observed_facts": ["已接收用户提交的文字或截图"],
                "likely_causes": [{"cause": "现场信息不足", "reason": "需要设备输出、错误码、目标地址或更完整截图。"}],
                "next_checks": ["补充完整错误信息或 CLI 输出", "说明故障发生前后的操作", "确认是否允许进入只读实时检查阶段"],
                "limitations": "这是本地 DEMO 模式的结构化示例，没有连接设备。",
            }
        return {"choices": [{"message": {"content": json.dumps(payload, ensure_ascii=False)}}]}


def _extract_json(content: str) -> dict[str, Any]:
    content = content.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", content, re.IGNORECASE | re.DOTALL)
    candidate = fenced.group(1).strip() if fenced else content
    try:
        value = json.loads(candidate)
    except json.JSONDecodeError:
        start, end = candidate.find("{"), candidate.rfind("}")
        if start < 0 or end <= start:
            raise RuntimeError("模型没有返回有效的诊断结果，请重试。")
        try:
            value = json.loads(candidate[start : end + 1])
        except json.JSONDecodeError as exc:
            raise RuntimeError("模型返回格式异常，请重试。") from exc
    if not isinstance(value, dict):
        raise RuntimeError("模型返回格式异常，请重试。")
    return value


def _string_list(value: Any, limit: int = 8) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value[:limit] if isinstance(item, str) and item.strip()]


def _normalize_result(value: dict[str, Any]) -> dict[str, Any]:
    causes = value.get("likely_causes", [])
    normalized_causes = []
    if isinstance(causes, list):
        for item in causes[:6]:
            if isinstance(item, dict):
                cause = item.get("cause")
                reason = item.get("reason")
                if isinstance(cause, str) and cause.strip():
                    normalized_causes.append({
                        "cause": cause.strip(),
                        "reason": reason.strip() if isinstance(reason, str) else "",
                    })
    return {
        "title": str(value.get("title") or "初步诊断").strip()[:120],
        "summary": str(value.get("summary") or "模型未提供摘要。").strip()[:1200],
        "observed_facts": _string_list(value.get("observed_facts")),
        "likely_causes": normalized_causes,
        "next_checks": _string_list(value.get("next_checks")),
        "limitations": str(value.get("limitations") or "本次分析未连接设备进行实时检查。").strip()[:800],
        "live_checks_performed": False,
    }


def diagnose_intake(
    *,
    question: str,
    image_name: str | None = None,
    image_type: str | None = None,
    image_bytes: bytes | None = None,
    client: BailianClient | DemoIntakeClient | None = None,
    vision_model: str | None = None,
    on_progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    question = question.strip()
    if len(question) > MAX_TEXT_LENGTH:
        raise ValueError(f"问题过长，请控制在 {MAX_TEXT_LENGTH} 个字符以内。")
    if not question and not image_bytes:
        raise ValueError("请先输入问题，或选择一张截图。")
    if image_bytes is not None:
        if not image_bytes:
            raise ValueError("截图为空，请重新选择图片。")
        if len(image_bytes) > MAX_IMAGE_BYTES:
            raise ValueError("截图不能超过 5 MB。")
        if image_type not in ALLOWED_IMAGE_TYPES:
            raise ValueError("截图格式请使用 PNG、JPG 或 WEBP。")

    progress = on_progress or (lambda _: None)
    progress("输入已校验，正在准备" + ("文字和截图" if image_bytes else "文字描述"))

    user_text = question or "请分析这张截图，指出可以直接确认的现象、可能原因和下一步检查。"
    content: Any = user_text
    if image_bytes is not None:
        encoded = base64.b64encode(image_bytes).decode("ascii")
        content = [
            {"type": "text", "text": user_text + f"\n附件截图文件名：{image_name or 'screenshot'}"},
            {"type": "image_url", "image_url": {"url": f"data:{image_type};base64,{encoded}"}},
        ]

    selected_client = client or BailianClient()
    progress("本地示例正在生成" if isinstance(selected_client, DemoIntakeClient) else "百炼 API 请求即将发送，等待模型分析返回…")
    response = selected_client.chat(
        [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ],
        temperature=0.2,
        max_tokens=1600,
        model=(None if image_bytes is None else vision_model or os.environ.get("DASHSCOPE_VISION_MODEL")),
    )
    progress("响应已返回，正在解析和校验诊断结果")
    if not isinstance(response, dict) or not isinstance(response.get("choices"), list) or not response["choices"]:
        raise RuntimeError("模型响应中没有有效的 choices，请检查 API 和模型配置。")
    if response["choices"][0].get("finish_reason") == "length":
        raise RuntimeError("模型结果超过输出长度，未生成完整诊断，请简化问题后重试。")
    message = ((response.get("choices") or [{}])[0].get("message") or {})
    model_content = message.get("content")
    if isinstance(model_content, list):
        model_content = "".join(
            str(part.get("text", "")) for part in model_content if isinstance(part, dict)
        )
    if not isinstance(model_content, str) or not model_content.strip():
        raise RuntimeError("模型没有返回诊断内容，请检查模型部署和 API 配置。")
    parsed = _extract_json(model_content)
    if not isinstance(parsed.get("summary"), str) or not parsed["summary"].strip():
        raise RuntimeError("模型返回的诊断缺少摘要，请重试。")
    return _normalize_result(parsed)
