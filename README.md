# NetPath-Doctor (初期 MVP)

## 项目范围说明
- 只做华为 VRP 设备，不做思科等其他厂商。
- 只处理 IPv4 基础连通性故障，不做复杂协议。
- 诊断 Agent 使用五类只读检查；故障注入和恢复由外层实验控制器完成。

## 中期准备材料

答辩大纲、讲稿、报告技术正文、代码导读和现场清单见 [材料入口](docs/midterm/README.md)。当前以本机 eNSP Console 为现场接入方式；SSH 端到端集成和大模型策略放入下一阶段。PPT 本阶段仅完成大纲。

## Benchmark

在仓库根目录执行 golden benchmark：

```powershell
python -m benchmarks.runner
```

当前 benchmark 覆盖 20 个案例，检查诊断结果、证据链和 Agent 动作顺序。详细说明见 `benchmarks/README.md`。
