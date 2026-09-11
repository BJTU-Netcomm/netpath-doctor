# NetPath-Doctor (初期 MVP)

## 项目范围说明
- 只做华为 VRP 设备，不做思科等其他厂商。
- 只处理 IPv4 基础连通性故障，不做复杂协议。
- 只开放五类只读动作，绝不允许执行配置修改命令[cite: 1]。

## Benchmark

在仓库根目录执行 golden benchmark：

```powershell
python -m benchmarks.runner
```

当前 benchmark 覆盖 20 个案例，检查诊断结果、证据链和 Agent 动作顺序。详细说明见 `benchmarks/README.md`。
