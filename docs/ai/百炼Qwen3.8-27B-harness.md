# 百炼 Qwen3.8-27B 接入说明

## 已验证内容

工作空间兼容接口已经完成真实请求验证：

- 模型：`qwen3.8-27b`
- 接口：`/compatible-mode/v1/chat/completions`
- Smoke test：返回 `run_ping` 工具调用，参数包含 `device` 和 `target_ip`
- Replay test：Qwen 调用只读工具并通过 `finish_diagnosis` 输出 `INTERFACE_DOWN`
- 验证记录：`reports/ai_trace/bailian_qwen38_27b_smoke_2026-10-14.json`、`reports/ai_trace/bailian_qwen38_27b_case001_replay_2026-10-14.json`

当前新增的离线契约验收：

```powershell
.\.venv\Scripts\python.exe -m benchmarks.ai_benchmark
```

结果为 20/20。它使用确定性 scripted planner 检查 harness 协议、只读边界、诊断证据校验和 `replay://` 来源，不作为 Qwen 准确率。历史 2026-10-14 的 CASE_001 trace 保留原样，不能作为盲测准确率证明。

记录来自 ReplayExecutor，不能表述为实时 eNSP 结果。实时 SSH/eNSP 接入仍由下一阶段完成。

### Qwen Replay 复测口径

真实 Qwen 批量评测使用短证据约束和 Replay 能力摘要：模型只会看到当前
manifest 中实际存在的观察动作、设备和接口组合，不能读取答案字段。Harness
把 `finish_diagnosis` 的 evidence 限制为最多 4 条、每条 120 个字符，并在
JSON 截断时把本地校验错误返回给模型重试。默认参数是 8 轮、768 output
tokens，可用 `--max-turns` 和 `--max-tokens` 调整。之前的 12/20 是修复前基线，
修复后必须重新运行并保存新的报告，不能直接沿用。

## 本地运行

在 PowerShell 中设置环境变量。API Key 只放在当前终端或未跟踪的本地配置中：

```powershell
$env:DASHSCOPE_API_KEY = "从百炼控制台复制的 Key"
$env:DASHSCOPE_BASE_URL = "https://ws-kke5jjchwyfk4mqu.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
$env:DASHSCOPE_MODEL = "qwen3.8-27b"
```

运行单轮工具调用：

```powershell
.\.venv\Scripts\python.exe -m tools.bailian_smoke
```

运行 CASE_001 的 AI Replay 诊断：

```powershell
.\.venv\Scripts\python.exe -m tools.bailian_replay_diagnosis `
  scenarios/golden/case_001_interface_down/scenario.json
```

拓扑已经在 eNSP 中启动并且三个本地 Console 端口可用时，可以运行只读现场诊断：

```powershell
.\.venv\Scripts\python.exe -m tools.bailian_live_diagnosis `
  scenarios/live/case_001_interface_down.local.json `
  --transport console `
  --devices config/ensp_console.local.json
```

如果后续 SSH 环境完成，只需切换传输层；AI 工具和 Parser 不变：

```powershell
.\.venv\Scripts\python.exe -m tools.bailian_live_diagnosis `
  scenarios/live/case_001_interface_down.local.json `
  --transport ssh `
  --devices config/devices.local.json
```

两个命令都只执行 `display`、`ping`、`tracert` 等观察动作，不会注入或恢复故障。故障实验仍应使用 `benchmarks.live_experiment`，并由外层控制器的 `finally` 恢复。

## 工具边界

模型只能看到以下观察工具：

```text
run_ping(device, target_ip)
run_tracert(device, target_ip)
check_route(device, destination)
check_interface(device, interface)
check_arp(device, target_ip)
finish_diagnosis(diagnosis)
request_more_data(missing_fields)
```

`finish_diagnosis` 和 `request_more_data` 只在本地校验结构，不会连接设备。模型没有通用命令、Shell、`shutdown`、路由删除或路由恢复工具。外层实验控制器仍负责故障注入和 `finally` 恢复。

## 安全与验收

- 工具名称、设备名和参数先通过 action catalog 校验；
- provider 返回后再次检查设备白名单、IPv4/接口格式、额外参数和换行注入；
- 每次工具结果统一为 `success / facts / raw_ref / error`；
- 完成诊断必须能和成功观察 facts 对应，未经观察的猜测会降级为 `NEED_MORE_DATA`；
- 结构化诊断中的 `fault_type` 归一为 V1 大写枚举；
- 证据不足或模型超时返回 `NEED_MORE_DATA`；
- 密钥不写入源代码、fixture、报告或 Git；
- 完成实时 SSH 接入后，必须重新采集真实 eNSP CLI 并单独标记 execution mode。
