# CASE_001：R2 到 R3 接口 Down

## 案例现象

PC1（`192.168.1.10`）无法访问 Server1（`192.168.3.10`）。

## 故障设置

R2 到 R3 的出接口 `GigabitEthernet0/0/1` 处于 `DOWN` 状态。

## 标准诊断流程

1. 对 `192.168.3.10` 执行 ping，结果为 100% 丢包。
2. 执行 tracert，最后可达设备为 R2。
3. 检查 R2 到目标地址的路由，路由存在。
4. 检查 R2 出接口 `GigabitEthernet0/0/1`，物理状态为 `DOWN`。
5. 输出 `INTERFACE_DOWN`。

## 文件说明

- `scenario.json`：场景输入和故障真值；
- `expected_result.json`：benchmark 标准答案；
- `mock_outputs.json`：当前 Mock Tool Server 的结构化返回；
- `ping.txt`、`tracert.txt`、`route_r2.txt`、`interface_r2_gigabitethernet0_0_1.txt`：原始 CLI 回显，供 Parser 阶段使用。
