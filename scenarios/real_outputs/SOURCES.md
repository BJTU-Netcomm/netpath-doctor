# 回显样例来源说明

集成日期：2026-10-12。“实测”指提供者标注为 eNSP 采集的记录，本次集成没有重新运行设备。

## 已接入的采集记录

提供者：李梦瑶。来源分支：feat/ensp-topology。
固定提交：46dae5185323e7f45fb3baaef1827001cc95da06。
原文保存在 docs/cli_records/；提供者标注采集日期为 2026-10-10。

| 原始文件（相对 docs/cli_records） | 设备 | 命令 | 状态 | 测试结论 |
|---|---|---|---|---|
| normal/normal_ping_R1.txt | R1 | ping 192.168.3.1 | 正常 | reachable=true，packet_loss=0 |
| normal/normal_tracert_R1.txt | R1 | tracert 192.168.3.1 | 正常 | 提取两个跳点，不单独证明全程到达 |
| normal/normal_route_R2.txt | R2 | display ip routing-table 192.168.3.0 | 正常 | 目标主机命中 /24 静态路由 |
| normal/normal_interface_R2.txt | R2 | display ip interface brief | 正常 | 不同于详细接口命令；CHECK_INTERFACE 返回解析失败 |
| normal/normal_arp_R2.txt | R2 | display arp | 正常 | 下一跳 10.0.23.2 有表项 |
| route_missing/route_missing_filter_R2.txt | R2 | display ip routing-table 192.168.3.0 | 删除静态路由后 | 空正文不能证明缺路由 |
| route_missing/route_missing_full_R2.txt | R2 | display ip routing-table | 删除静态路由后 | 完整表含 13 条路由，无覆盖目标的路由 |
| route_missing/route_missing_ping_R1.txt | R1 | ping 192.168.3.1 | 删除静态路由后 | reachable=false，packet_loss=100 |

测试文件 tests/test_ensp_cli_records.py 直接读取以上记录。截断副本和 CRLF 副本是测试变体，不算新增实测采集。

## 两份实测路由 fixture

以下文件逐字节复制自上述固定提交，替代之前从报告或行为说明提取的版本：

| fixture（相对 scenarios/real_outputs） | 原始记录（相对 docs/cli_records） |
|---|---|
| routing-table/route_r2_route_present_ensp.txt | normal/normal_route_R2.txt |
| routing-table/route_r2_empty_body_ensp.txt | route_missing/route_missing_filter_R2.txt |

第二份记录的实际查询参数为 192.168.3.0，不是 192.168.3.1。空正文必须返回解析失败；过滤查询到完整表的回退由传输层完成。

## 构造样例

其余 TXT 文件及 tests/test_real_vrp_outputs.py 源自邓予钦提交 4d571461f7f37219298491df2c70ae0d5c26e524（feat/agent-controller）。除上述两份 _ensp.txt 外，本目录 TXT 文件均为构造样例，不能作为实际设备实验次数或采集完成度的证据。

## 尚待补齐

- R2 display interface GigabitEthernet0/0/1 正常、shutdown 后、恢复后的完整原文。
- 故障态 tracert 完整回显；ARP 空表实测记录及其采集状态。
- 如需声称验证了实测分页符，须提供包含分页符的采集原文。
- SSH 三轮实验完整 ping 统计、可靠的路由缺失验证、恢复失败记录仍由实验负责人补齐。
