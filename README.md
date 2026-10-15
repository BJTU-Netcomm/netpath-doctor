# NetPath-Doctor (初期 MVP)

## 项目范围说明
- 只做华为 VRP 设备，不做思科等其他厂商。
- 只处理 IPv4 基础连通性故障，不做复杂协议。
- 诊断 Agent 使用五类只读检查；故障注入和恢复由外层实验控制器完成。

## 中期准备材料

答辩大纲、讲稿、报告技术正文、代码导读和现场清单见 [材料入口](docs/midterm/README.md)。当前以本机 eNSP Console 为现场接入方式；AI 接入阶段先使用百炼 API/Qwen 和 Replay harness，再接 eNSP 只读观察，SSH 仍放在后续阶段。AI 任务书见 docs/ai/AI-harness中期任务书_2026-10.md，百炼运行说明见 docs/ai/百炼Qwen3.8-27B-harness.md。

## Benchmark

在仓库根目录执行 golden benchmark：

```powershell
python -m benchmarks.runner
```

当前 benchmark 覆盖 20 个案例，检查诊断结果、证据链和 Agent 动作顺序。详细说明见 `benchmarks/README.md`。

AI tool/harness 契约 Benchmark：

```powershell
python -m benchmarks.ai_benchmark
```

当前 20/20 通过。该结果使用确定性 scripted planner 检查只读工具、证据校验和 `replay://` 来源追踪，不代表 Qwen 的模型准确率；真实 Qwen 运行需要单独保存模型、延迟和 tool trace。

