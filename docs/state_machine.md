# NetPath-Doctor 最小诊断状态机

## 1. 目的

本状态机用于描述 NetPath-Doctor 在初期 MVP 中的基础诊断流程。

当前阶段仅支持：

- Huawei VRP
- IPv4 基础连通性故障
- 固定拓扑 PC1—R1—R2—R3—Server1
- 四类故障：
  - INTERFACE_DOWN
  - ROUTE_MISSING
  - NEXT_HOP_UNREACHABLE
  - ARP_UNRESOLVED

---

## 2. 状态定义

### INIT

开始诊断，读取 scenario.json。

↓

### PING_TEST

执行 RUN_PING。

如果 ping 成功：

FINISH_NORMAL

如果 ping 失败：

TRACE_PATH

↓

### TRACE_PATH

执行 RUN_TRACERT。

根据 tracert 结果确定最后可达设备和疑似故障位置。

↓

### LOCATE_SUSPECT

确定需要进一步检查的设备。

↓

### CHECK_ROUTE

执行 CHECK_ROUTE。

如果：

route_found = false

则诊断为：

ROUTE_MISSING

如果：

route_found = true

则继续检查接口。

↓

### CHECK_INTERFACE

执行 CHECK_INTERFACE。

如果：

physical_status = DOWN

则诊断为：

INTERFACE_DOWN

如果：

physical_status = UP

则继续检查 ARP。

↓

### CHECK_ARP

执行 CHECK_ARP。

如果：

entry_found = false

则诊断为：

ARP_UNRESOLVED

如果当前证据仍然不足：

REQUEST_MORE_DATA

↓

### FINISH_DIAGNOSIS

输出最终诊断结果。

---

## 3. CASE_001 预期流程

CASE_001：

PC1 无法访问 Server1。

诊断流程：

1. RUN_PING
2. RUN_TRACERT
3. CHECK_ROUTE
4. CHECK_INTERFACE
5. FINISH_DIAGNOSIS

预期最终结果：

- fault_device: R2
- fault_type: INTERFACE_DOWN
- fault_interface: GigabitEthernet0/0/1
