# NetPath-Doctor AI Harness 中期任务书

**版本**：V2.0
**更新时间**：2026-10-14
**适用分支**：feat/midterm-integration
**用途**：供组员、导师和代码辅助 AI 阅读、执行和验收

---

## 1. 项目目标变更

### 原阶段目标

原目标是完成一个可解释的 eNSP 网络故障诊断原型：搭建 R1-R2-R3 拓扑、解析 Huawei VRP CLI、诊断 INTERFACE_DOWN 和 ROUTE_MISSING、完成离线 Benchmark、故障注入恢复和中期答辩材料。

### 导师新增目标

项目要进一步发展为一个可以接入网络模拟器、由 AI 调用网络工具、根据设备反馈提取证据并完成故障判断的 tool/harness。

~~~text
模拟器或真实设备
        ↓
Transport
        ↓
只读网络工具
        ↓
VRP Parser
        ↓
结构化 facts
        ↓
Qwen / 百炼 API
        ↓
工具选择与故障判断
        ↓
Policy 校验、审计日志、Benchmark
~~~

中期增加 AI 决策层，但不要求中期完成自主修复或 8B 微调。最终目标才包括多 transport、8B 基座评测和 LoRA/QLoRA 微调。

## 2. 当前已完成基线

可以直接复用：

- R1-R2-R3 eNSP 拓扑；
- Huawei VRP Parser；
- ping、tracert、routing-table、interface、ARP 五类解析；
- 规则状态机、动作 schema；
- ReplayExecutor、ENSPConsoleTransport、SSHTransport；
- INTERFACE_DOWN 和 ROUTE_MISSING 实验入口；
- 108 个单元测试，另有 4 个子测试；
- CLI Replay Benchmark 20/20；
- AI tool contract Benchmark 20/20（确定性 scripted planner，不作为 Qwen 准确率）；
- 中期报告、讲稿、PPT 和答疑材料。

事实字段继续冻结：

~~~text
reachable
packet_loss
route_found
physical_status
protocol_status
entry_found
last_reachable_device
~~~

诊断字段继续冻结：

~~~text
diagnosis_status
fault_type
fault_device
fault_interface
target_network
evidence
~~~

不得在 AI 接入时擅自引入 target_unreachable 等新字段。

## 3. AI harness 设计

第一版只允许模型调用五个只读观察工具，另提供两个本地终止工具：

~~~text
run_ping(device, target_ip)
run_tracert(device, target_ip)
check_route(device, destination)
check_interface(device, interface)
check_arp(device, target_ip)
finish_diagnosis(diagnosis)
request_more_data(missing_fields)
~~~

每个工具返回：

~~~json
{
  "success": true,
  "facts": {},
  "raw_ref": "reports/ai_trace/case001/ping.txt",
  "error": null
}
~~~

模型不得直接执行 shutdown、undo shutdown、undo ip route-static、ip route-static、任意 shell 或未注册设备命令。故障注入和恢复由外层实验控制器执行，并保证 finally 恢复。

AI 决策循环：

~~~text
读取 case
→ Qwen 选择只读工具
→ Policy 校验名称、设备和参数
→ Transport 执行
→ Parser 解析 CLI
→ 返回 facts 和 raw_ref
→ 最多重复 8 个模型回合
→ 校验最终诊断 JSON 和证据来源
→ 保存完整 trace
~~~

证据不足必须返回 NEED_MORE_DATA。

## 4. 中期目标与验收

### 环境验收

集成机可以执行：

~~~text
设置本地环境变量 DASHSCOPE_API_KEY
运行 python tools/bailian_smoke.py
模型默认使用 Qwen3.8 27B；如果百炼控制台显示的模型 ID 不同，以控制台 ID 为准，并通过 DASHSCOPE_MODEL 覆盖。
~~~

导师 PydanticAI 示例成功运行 10 次。每次保存 model、prompt、tool call、tool result、response、elapsed_ms、error。

### Replay AI Benchmark

原有 20 个 CLI Replay case 继续作为回归基线；AI tool contract Benchmark 使用同一批 6 个独立 golden case 加 14 个参数化变体，覆盖正常、INTERFACE_DOWN、ROUTE_MISSING、ARP_UNRESOLVED、NEXT_HOP_UNREACHABLE 和 NEED_MORE_DATA。

| 指标 | 中期门槛 |
|---|---:|
| 原有 CLI Benchmark | 20/20，不退化 |
| 工具调用 JSON 可解析率 | 100% |
| 非法工具调用率 | 0% |
| 证据来源可追溯率 | 100% |
| Qwen INTERFACE_DOWN 识别率 | 现场盲测后统计 |
| Qwen ROUTE_MISSING 识别率 | 现场盲测后统计 |
| Qwen NEED_MORE_DATA 识别率 | 现场盲测后统计 |
| 最大工具调用次数 | 不超过 8 个模型回合 |
| 规则 fallback | 可运行 |

20/20 指 Replay case，不代表 20 次真实 eNSP 实验。

### eNSP 现场增强

~~~text
启动 R1-R2-R3
→ baseline ping
→ 外层控制器注入故障
→ Qwen 调用只读工具
→ 输出结构化诊断
→ 外层控制器恢复
→ 保存报告
~~~

两类故障当前版本各连续 3 次。每次有原始 CLI、Parser facts、Qwen tool trace、最终 JSON、恢复结果、时间和 git commit。

## 5. 三人唯一负责的任务

### 段振阳：AI 集成、实验闭环和主讲

负责百炼 API 配置、PydanticAI 示例、百炼 API 适配器、Agent 循环、AI 与 Parser/StateMachine/Replay 的连接、eNSP Console 演示、PPT 讲稿和答辩主讲。

必须交付：

~~~text
ai/bailian_client.py
ai/network_agent.py
ai/schemas.py
tests/test_ai_agent_loop.py
reports/ai_trace/
docs/ai/AI现场演示步骤.md
~~~

验收：Qwen 至少调用一个网络工具；Replay 完成一次完整诊断；输出现有字段；模型失败可回退规则状态机；现场可演示三种状态；不宣称自主修复。

### 李梦瑶：工具 harness、安全策略和设备实验控制

负责五个只读工具、工具 schema、注册表、设备和参数白名单、超时重试、最大步数、故障注入恢复、eNSP 原始回显和截图。

必须交付：

~~~text
harness/tool_registry.py
harness/policy.py
tests/test_tool_policy.py
docs/ai/tool-contract.md
docs/cli_records/
reports/live/
~~~

验收：五个工具支持 Replay；非法工具、设备和参数被拒绝；超时不死循环；注入后进入恢复流程；每次现场有原始回显和恢复记录。

### 邓予钦：Parser、数据集和 AI Benchmark

负责真实 VRP 回显、facts 一致性、三态 interface 检查、Replay/tool-call 数据集、AI Benchmark，以及规则、Qwen 基座和微调模型对比。

必须交付：

~~~text
tests/test_ai_tool_calls.py
benchmarks/ai_replay_benchmark.py
data/ai_replay/
reports/ai_benchmark/
docs/ai/parser-ai-validation.md
~~~

验收：三态解析正确；旧 pytest 和 20/20 不退化；20 个 Replay case 有标签；证据能追溯 facts；区分 Replay、历史现场和当前现场结果；不把构造样例写成实测。

## 6. 依赖顺序

~~~text
李梦瑶完成工具契约和 Replay 工具
→ 邓予钦固定 Parser facts 和 Benchmark 数据
→ 段振阳接入百炼 API 和 Agent
→ 三人检查 Replay 20-case
→ 段振阳接 eNSP Console
→ 李梦瑶执行注入恢复并保存原文
→ 邓予钦解析和统计
→ 段振阳完成演示和答辩
~~~

每个文件、报告和指标只能有一个负责人。

## 7. AI 辅助开发规则

1. 先检查分支、工作区和已有实现；
2. 不覆盖 Parser、Benchmark 和现场证据；
3. 不虚构 eNSP、SSH、Qwen 或微调结果；
4. 不把 Replay 输出称为真实设备输出；
5. 不改变 V1 字段，除非更新 data contract；
6. 不开放 shell 或任意配置命令；
7. 所有 tool call 写入 trace；
8. 写操作由外层控制器执行并保证恢复；
9. 测试失败时报告真实错误；
10. 修改后运行测试并记录 commit。

## 8. 本周清单

### 段振阳

- [x] 配置百炼 API key（只放环境变量）；
- [x] 运行 Qwen3.8 27B；
- [ ] 复现 PydanticAI 示例；
- [ ] 创建 feat/bailian-agent；
- [x] 完成只读工具 Agent 循环；
- [x] 输出第一份 AI trace；
- [x] 增加工具参数、诊断字段和 evidence provenance 的本地校验。

### 李梦瑶

- [x] 提交五个只读工具接口；
- [x] 提交工具白名单和参数校验；
- [x] 确认写操作不被 AI 调用；
- [ ] 补齐 interface 三态原文；
- [ ] 保存一轮完整现场原文。

### 邓予钦

- [ ] 固定 AI 工具 facts schema；
- [ ] 建立 20 个 Replay case 标签；
- [x] 编写工具调用 JSON 校验；
- [x] 编写 AI tool contract Benchmark；
- [x] 确认旧 Benchmark 20/20 不退化；
- [x] 输出第一份 AI 契约评测报告；

## 9. 导师汇报统一表述

> 我们保留可解释的 Parser 和规则状态机，把 Qwen 接入为受控决策层。当前先在 Replay 数据上完成工具调用和结构化诊断，再接入 eNSP 的只读观察链路；故障注入与恢复由可审计的外层 harness 控制。最终阶段再用真实 CLI 和工具轨迹构造数据，对开源 8B instruct 模型进行 LoRA/QLoRA 微调，并在留出 Benchmark 和现场拓扑上比较效果。
