# Benchmark

Benchmark 用 golden scenario 检查 Agent 是否能从固定诊断事实得到预期结果。每个案例都是一个独立目录，标准答案与输入分开保存，避免测试代码里硬编码故障结论。

## 运行

在仓库根目录执行：

```powershell
python -m benchmarks.runner
```

保存机器可读报告：

```powershell
python -m benchmarks.runner --output reports/benchmark_latest.json
```

程序会扫描 `scenarios/golden/*`，对每个案例执行当前状态机，并比较：

- 诊断状态；
- 故障设备、类型和接口；
- 标准答案要求的证据；
- Agent 实际动作顺序；
- 需要更多数据时的字段列表。

当前案例覆盖：

| 案例 | 预期结果 | 覆盖路径 |
|---|---|---|
| `CASE_001` | `INTERFACE_DOWN` | 路由存在，接口物理状态 DOWN |
| `CASE_002` | `ROUTE_MISSING` | 目标路由不存在 |
| `CASE_003` | `ARP_UNRESOLVED` | 路由和接口正常，但 ARP 缺失 |
| `CASE_004` | `NORMAL` | 初始 ping 成功 |
| `CASE_005` | `NEED_MORE_DATA` | 现有只读证据不足以继续收敛 |
| `CASE_006` | `NEXT_HOP_UNREACHABLE` | 路由存在，但下一跳不可达 |

退出码为 `0` 表示所有案例通过，退出码为 `1` 表示至少一个案例失败。六个案例都通过 `log_manifest.json` 关联原始 CLI 日志，并使用 `ReplayExecutor` 调用 Parser；`mock_outputs.json` 仅保留为单元测试和故障隔离时的备用数据。benchmark 运行时会移除 `ground_truth`，它只用于人工检查案例定义，Agent 无法读取标准答案。
