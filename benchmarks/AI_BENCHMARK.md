# AI Tool Contract Benchmark

运行：

```powershell
.\.venv\Scripts\python.exe -m benchmarks.ai_benchmark
```

该 Benchmark 使用 6 个独立 golden case 加 14 个参数化 Replay case、`ReplayExecutor` 和确定性的 scripted planner，验收 AI harness 的工具协议，不宣称 Qwen 的诊断准确率。它检查：

- 诊断字段是否与标准结果一致；
- 终止动作是否为 `finish_diagnosis` 或 `request_more_data`；
- 没有写操作工具；
- 每个成功观察结果都有 `replay://...` 来源；
- V1 的 `target_network`、`target_ip`、`next_hop` 字段是否保持一致。

真实 Qwen 评测需要另存 provider、模型、延迟、原始 tool trace，并与本协议 Benchmark 分开报告。

有百炼环境变量时运行真实 Qwen Replay：

```powershell
.\.venv\Scripts\python.exe -m benchmarks.qwen_replay_benchmark
```

真实 Qwen Replay 默认使用 `--max-turns 8 --max-tokens 768`。如需复现旧的
384-token 基线，可显式传入 `--max-tokens 384`。报告会记录这两个参数；模型
通过率仍需以实际 provider 运行结果为准，不能用 scripted planner 代替。

该命令缺少 `DASHSCOPE_API_KEY` 时会直接报配置缺失，不会生成伪造的模型结果。
