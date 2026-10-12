# 2026-10-12 中期集成验证记录

当前工作分支：`feat/midterm-integration`，基于 `4547c47`。
本次完成 CLI 采集证据与 Parser 测试的选择性集成，没有运行新的现场故障实验。

## 已接入

- 李梦瑶 `46dae5185323e7f45fb3baaef1827001cc95da06`：8 份 CLI 原文及采集说明，位于 `docs/cli_records/`。
- 邓予钦 `4d571461f7f37219298491df2c70ae0d5c26e524`：构造样例、路由 fixture 和 19 个 Parser 测试。来源分支是 `feat/agent-controller`。
- 新增 `tests/test_ensp_cli_records.py`：10 个测试，读取已提交的采集原文，并验证截断与 CRLF 变体。
- 修正两份实测路由 fixture 的来源，直接复制已提交原文；完整来源映射见 `scenarios/real_outputs/SOURCES.md`。

## 实际验证结果

在项目目录执行：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m benchmarks.runner
```

结果：`96 passed, 4 subtests passed`；Golden Replay Benchmark `20/20`，`all_passed=true`。

新增 29 个测试相对于原有 67 个测试。测试数不是故障类型数，也不是现场实验次数。
Parser、传输层、诊断状态机和 V1 字段在本次集成中未修改。

## 这些结果说明什么

1. 已提交的正常与路由缺失 ping 原文能解析出 0% / 100% 丢包。
2. 已提交的正常 tracert、目标路由和 ARP 原文能提取对应字段。
3. R2 的空过滤路由回显不会被当成缺路由证据；完整表中的 13 条路由可用于确认目标没有匹配路由。
4. 人为删去一条路由形成的不完整表会被拒绝，防止假阳性。
5. 当前详细接口解析器会拒绝 `display ip interface brief` 格式；这一拒绝测试通过，不能称为详细接口实测适配完成。

## 尚未完成的现场证据

- 李梦瑶：详细接口命令正常、关闭、恢复后的完整采集原文；SSH 三轮实验完整 ping 统计、路由缺失验证及恢复异常报告；已提交账号密码的更换及本地化配置。
- 邓予钦：收到详细接口原文后补充对应 fixture 和测试；其他异常状态的实测样例继续按来源分类。
- 组长：现场复现两种故障，保存同一次运行的 JSON、原始回显和演示录像，然后冻结答辩版本。

诊断主线目前采用本地 Console 和规则状态机，没有调用大模型。SSH 自动注入恢复实验与诊断主线应分别描述。

## 可用于汇报的一句话

我们已经把队友提交的设备原始回显接入集成分支的解析回归测试，全部 96 个测试和 20 个离线场景通过；详细接口故障态采集、SSH 实验的完整证据及最终现场复现仍在收尾。
