"""Run the local diagnosis console: python -m tools.diagnosis_server."""

from __future__ import annotations

import base64
import json
import os
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if __package__ in {None, ""}:
    sys.path.insert(0, str(ROOT))

from ai.bailian_client import BailianClient
from ai.console_config import ConsoleConfig
from ai.intake_diagnosis import DemoIntakeClient, diagnose_intake
from ai.live_console import LiveConsoleService

WEB_ROOT = ROOT / "web" / "diagnosis_console"


class DiagnosisServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, settings=None):
        super().__init__(address, DiagnosisHandler)
        self.settings = settings or ConsoleConfig(ROOT)
        self.diagnosis_lock = threading.Lock()
        self.live = LiveConsoleService(ROOT)
        self.active_fault = None


class DiagnosisHandler(BaseHTTPRequestHandler):
    server_version = "NetPathDoctor/0.3"

    def log_message(self, format, *args):
        print(f"[ui] {self.address_string()} - {format % args}")

    def _headers(self, code, mime):
        self.send_response(code)
        self.send_header("Content-Type", mime)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data: blob:; connect-src 'self'; frame-ancestors 'none'")
        self.end_headers()

    def _json(self, code, data):
        self._headers(code, "application/json; charset=utf-8")
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def _local_request(self):
        port = self.server.server_port
        hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        origin = self.headers.get("Origin")
        if self.headers.get("Host") not in hosts or (origin and origin not in {f"http://{host}" for host in hosts}):
            self._json(403, {"ok": False, "error": "仅接受本机页面的请求。"})
            return False
        return True

    def do_GET(self):
        if not self._local_request():
            return
        if self.path == "/api/health":
            self._json(200, {"ok": True, **self.server.settings.public(), "ensp": self.server.live.summary(),
                             "active_fault": self.server.active_fault})
            return
        static = {"/": ("index.html", "text/html; charset=utf-8"),
                  "/index.html": ("index.html", "text/html; charset=utf-8"),
                  "/assets/app.css": ("assets/app.css", "text/css; charset=utf-8"),
                  "/assets/app.js": ("assets/app.js", "text/javascript; charset=utf-8")}
        if self.path not in static:
            self._json(404, {"ok": False, "error": "Not found"})
            return
        name, mime = static[self.path]
        self._headers(200, mime)
        self.wfile.write((WEB_ROOT / name).read_bytes())

    def do_POST(self):
        if not self._local_request():
            return
        if self.path not in {"/api/config", "/api/check-provider", "/api/diagnose", "/api/ensp/preflight", "/api/fault"}:
            self._json(404, {"ok": False, "error": "Not found"})
            return
        try:
            if self.headers.get("Content-Type", "").split(";", 1)[0] != "application/json":
                raise ValueError("请求必须使用 application/json。")
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 8 * 1024 * 1024:
                raise ValueError("请求内容为空或超过 8 MB。")
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(body, dict):
                raise ValueError("请求必须为 JSON 对象。")
            if self.path == "/api/config":
                self.server.settings.update(body)
                self._json(200, {"ok": True, **self.server.settings.public()})
            elif self.path == "/api/fault":
                self._fault(body)
            elif self.path == "/api/check-provider":
                self._check_provider()
            elif self.path == "/api/ensp/preflight":
                if not self.server.diagnosis_lock.acquire(blocking=False):
                    self._json(409, {"ok": False, "error": "诊断执行中，请完成后再检测设备。"})
                    return
                try:
                    self._json(200, {"ok": True, **self.server.live.preflight()})
                finally:
                    self.server.diagnosis_lock.release()
            else:
                self._diagnose(body)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except (ValueError, RuntimeError, UnicodeError) as exc:
            self._json(400, {"ok": False, "error": self.server.settings.error_message(exc)})
        except Exception as exc:
            print(f"[ui] request failed: {type(exc).__name__}")
            self._json(500, {"ok": False, "error": "服务处理失败，请检查本地配置或重试。"})

    def _fault(self, body):
        action = body.get("action")
        fault_type = body.get("fault_type")
        if not isinstance(action, str) or action not in {"inject", "recover"} \
                or not isinstance(fault_type, str) or fault_type not in {"INTERFACE_DOWN", "ROUTE_MISSING"}:
            raise ValueError("请选择支持的故障操作和类型。")
        if not self.server.diagnosis_lock.acquire(blocking=False):
            self._json(409, {"ok": False, "error": "当前有诊断或设备检查正在执行，请完成后重试。"})
            return
        try:
            active = self.server.active_fault
            if action == "inject":
                if active:
                    raise ValueError(f"当前已有 {active} 故障，请先恢复后再注入。")
                result = self.server.live.inject_fault(fault_type)
                self.server.active_fault = fault_type
            else:
                if active and active != fault_type:
                    raise ValueError(f"当前记录的故障为 {active}，请选择相同类型恢复。")
                result = self.server.live.recover_fault(fault_type)
                self.server.active_fault = None
            self._json(200, {"ok": True, "result": result, "active_fault": self.server.active_fault})
        finally:
            self.server.diagnosis_lock.release()

    def _check_provider(self):
        config, _ = self.server.settings.client_config()
        started = time.perf_counter()
        response = BailianClient(config).chat(
            [{"role": "user", "content": "连接测试，请仅回复 OK。"}], max_tokens=32)
        choices = response.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0].get("message"), dict):
            raise RuntimeError("接口未返回有效模型响应，请检查模型 ID。")
        with self.server.settings.lock:
            current = self.server.settings.values
            if current["model"] == config.model and current["api_key"] == config.api_key and current["base_url"] == config.base_url:
                self.server.settings.verified = True
        self._json(200, {"ok": True, "model": config.model,
                         "elapsed_ms": round((time.perf_counter() - started) * 1000),
                         "message": "百炼 API 已返回有效响应。此测试验证文字调用，截图能力需要另行测试。"})

    def _diagnose(self, body):
        if body.get("diagnosis_kind") == "live":
            self._diagnose_live(body)
            return
        question = body.get("question", "")
        if not isinstance(question, str):
            raise ValueError("问题必须为文本。")
        image_type, image_bytes = None, None
        image_data = body.get("image_data")
        if image_data:
            if not isinstance(image_data, str):
                raise ValueError("截图数据格式不正确。")
            header, sep, encoded = image_data.partition(",")
            if not sep or not header.startswith("data:image/") or not header.endswith(";base64"):
                raise ValueError("截图数据格式不正确。")
            image_type = header[5:].split(";", 1)[0]
            image_bytes = base64.b64decode(encoded, validate=True)
        settings = self.server.settings.public()
        mode = settings["mode"]
        vision_model = None
        if mode == "demo":
            client = DemoIntakeClient()
            model = "LOCAL DEMO"
        else:
            config, vision_model = self.server.settings.client_config()
            client = BailianClient(config)
            model = vision_model if image_bytes and vision_model else config.model
        if not self.server.diagnosis_lock.acquire(blocking=False):
            self._json(409, {"ok": False, "error": "已有诊断正在执行，请等待完成。"})
            return
        streaming = body.get("stream") is True
        started = time.perf_counter()

        def emit(data):
            self.wfile.write((json.dumps(data, ensure_ascii=False) + "\n").encode("utf-8"))
            self.wfile.flush()

        try:
            if streaming:
                self._headers(200, "application/x-ndjson; charset=utf-8")
                emit({"event": "progress", "message": "收到！开始诊断…", "mode": mode, "model": model})
            result = diagnose_intake(
                question=question, image_name=body.get("image_name"), image_type=image_type,
                image_bytes=image_bytes, client=client, vision_model=vision_model,
                on_progress=(lambda message: emit({"event": "progress", "message": message})) if streaming else None,
            )
            result.update({"execution_mode": mode, "model": model,
                           "elapsed_ms": round((time.perf_counter() - started) * 1000)})
            payload = {"ok": True, "result": result}
            if streaming:
                emit({"event": "result", **payload})
            else:
                self._json(200, payload)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as exc:
            message = self.server.settings.error_message(exc)
            if streaming:
                emit({"event": "error", "error": message})
            else:
                self._json(400, {"ok": False, "error": message})
        finally:
            self.server.diagnosis_lock.release()

    def _diagnose_live(self, body):
        if body.get("image_data"):
            raise ValueError("实时诊断使用设备回显，请移除截图；分析图片请切换材料分析。")
        if self.server.settings.public()["mode"] != "api":
            raise ValueError("eNSP 实时诊断需要真实 API，请在 API 设置中切换模式。")
        config, _ = self.server.settings.client_config()
        if not self.server.diagnosis_lock.acquire(blocking=False):
            self._json(409, {"ok": False, "error": "已有诊断正在执行，请等待完成。"})
            return
        streaming = body.get("stream") is True
        def emit(data):
            # API and tool errors are not permitted to reflect the provider key.
            rendered = json.dumps(data, ensure_ascii=False).replace(config.api_key, "[redacted]")
            self.wfile.write((rendered + "\n").encode("utf-8"))
            self.wfile.flush()
        try:
            if streaming:
                self._headers(200, "application/x-ndjson; charset=utf-8")
                emit({"event": "progress", "message": "收到！准备连接 eNSP 设备，开始只读诊断…"})
            summary = self.server.live.summary()
            report = self.server.live.diagnose(
                source=body.get("source_device", summary["source"]),
                target_ip=body.get("target_ip", summary["target_ip"]),
                question=body.get("question", ""), client=BailianClient(config),
                emit=emit if streaming else None)
            payload = {"ok": True, "result": report}
            if streaming:
                emit({"event": "result", **payload})
            else:
                self._json(200, payload)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as exc:
            error = self.server.settings.error_message(exc)
            if streaming:
                emit({"event": "error", "error": error})
            else:
                self._json(400, {"ok": False, "error": error})
        finally:
            self.server.diagnosis_lock.release()


def main():
    port = int(os.environ.get("NETPATH_UI_PORT", "8767"))
    try:
        server = DiagnosisServer(("127.0.0.1", port))
    except OSError:
        print(f"端口 {port} 无法监听，请关闭原诊断台，或设置 NETPATH_UI_PORT 使用其他端口。")
        return 1
    url = f"http://127.0.0.1:{port}/"
    print(f"NetPath-Doctor: {url}\n在网页右上角 API 设置中配置百炼。Ctrl+C 停止。")
    if os.environ.get("NETPATH_UI_OPEN", "1") != "0":
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
