# real_outputs（回显样例库）

本目录存放 Parser 兼容性测试使用的 CLI 回显样例，按来源严格区分两类：

1. **构造样例（synthetic）**：基于公开的华为 VRP 回显格式由本地编写生成，用于验证
   `Route Count : 0`、`Administratively Down`、分页、空表、超时行等关键格式的解析。
2. **eNSP 实测采集（ensp_captured）**：从 eNSP 实验机真实抓取、经脱敏后的回显，附设备、命令与故障状态标注。

> 实测采集样例的来源逐份登记在 [`SOURCES.md`](./SOURCES.md)，命名以 `_ensp.txt` 结尾。
> 两类样例都在 `tests/test_real_vrp_outputs.py` 中直接读取断言。

## 目录结构

```text
real_outputs/
├── README.md
├── SOURCES.md     # 实测采集样例的来源说明（设备/命令/故障状态/原始记录）
├── ping/          # 正常 / 100% 丢包
├── tracert/       # 全程可达 / 中途超时
├── routing-table/ # 有路由 / Route Count 0 / 默认路由 / 最长前缀 / 完整表无匹配 / 不完整表 / 实测
├── interface/     # UP / DOWN / Administratively Down
└── arp/           # 有表项 / 空表(Total:0)
```

## 样例清单与来源标注

### routing-table（display ip routing-table / display ip routing-table <IP>）

| 文件 | 来源 | 模拟故障/场景 |
|---|---|---|
| `route_missing_routecount0.txt` | 构造 | 无路由，`Summary Count : 0` |
| `route_missing_realcount0.txt` | 构造 | 无路由，真实 `Route Count : 0` |
| `route_exists.txt` | 构造 | 目标路由存在 |
| `route_full_longest_prefix.txt` | 构造 | 完整表，最长前缀匹配 / 默认路由 |
| `route_default_only.txt` | 构造 | 仅默认路由 0.0.0.0/0 |
| `route_no_match_complete.txt` | 构造 | 完整表无匹配（→ route_found=false） |
| `route_incomplete_mismatch.txt` | 构造 | `Routes` 计数与条目不符（→ 不可信，勿误判） |
| `route_r2_route_present_ensp.txt` | **实测** | R2 目标路由存在（ROUTE_MISSING 注入前） |
| `route_r2_empty_body_ensp.txt` | **实测** | R2 过滤查询空正文（注入后，→ 解析失败，非 route_found=false） |

### interface（display interface GigabitEthernet0/0/1）

| 文件 | 来源 | 状态 |
|---|---|---|
| `interface_administratively_down.txt` | 构造 | Administratively Down（归一 DOWN） |
| `interface_up.txt` | 构造 | UP/UP（正常） |

### arp（display arp <IP>）

| 文件 | 来源 | 场景 |
|---|---|---|
| `arp_empty_total0.txt` | 构造 | 空表 `Total:0`（entry_found=false） |
| `arp_entry_exists.txt` | 构造 | 命中表项（entry_found=true） |

### ping / tracert

| 文件 | 来源 | 场景 |
|---|---|---|
| `ping/ping_100pct_loss.txt` | 构造 | 100% 丢包（reachable=false） |
| `ping/ping_ok.txt` | 构造 | 正常连通（reachable=true） |
| `tracert/tracert_interrupted.txt` | 构造 | 中途超时（suspect_device=R2） |

## eNSP 实测采集进度

- [x] routing-table：R2 目标路由存在（`docs/cli_records/normal/normal_route_R2.txt`）
- [x] routing-table：R2 过滤查询空正文（`docs/cli_records/route_missing/route_missing_filter_R2.txt`）
- [x] ping：正常 / 100% 丢包，原文位于 docs/cli_records，已接入 test_ensp_cli_records.py。
- [x] tracert：正常态记录的跳点提取；故障态超时实测待补。
- [ ] interface：R2 出接口 UP / Administratively Down（含分页）
- [x] arp：R2 命中下一跳表项；空表实测待补。

来源提供者：李梦瑶（feat/ensp-topology）。样例命名：`<command>_<device>_<state>_ensp.txt`。

完整原始文件清单与局限见 SOURCES.md。CLI 原文由 tests/test_ensp_cli_records.py 测试；本目录构造样例由 tests/test_real_vrp_outputs.py 测试。接口简表的拒绝测试通过不代表详细接口实测适配完成。
