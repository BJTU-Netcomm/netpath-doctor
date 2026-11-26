# NetPath-Doctor (初期 MVP)

## 浏览器诊断台

双击 `start_diagnosis_console.cmd`，或运行 `python -m tools.diagnosis_server`，打开 `http://127.0.0.1:8767/`。
默认选择 **eNSP 实时诊断**，配置百炼后可选择源路由器和目标 IP，通过现有 AIHarness + LiveExecutor + Console 进行真实只读诊断，并查看工具回显和导出报告。
实时模式提供两种预设故障的一键注入与恢复，操作前检查基线，操作后用设备回显验证；故障会保留到手动恢复，适合先注入再启动诊断展示。
也可切换 **材料分析** 提交文字/图片。右上角 **API 设置** 可配置百炼接口、模型和密钥并检测连接。
配置、启动与录屏步骤见 [诊断台使用说明](docs/ai/诊断台使用说明.md)。

## 项目范围说明
- 只做华为 VRP 设备，不做思科等其他厂商。
- 只处理 IPv4 基础连通性故障，不做复杂协议。
- 诊断 Agent 使用五类只读检查；网页故障控制只开放预设实验故障，任意设备命令仍由外层实验控制流程管理。

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

