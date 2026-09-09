# NetPath-Doctor 数据契约 (Data Contract) V1.0

本文档明确了系统四部分的数据交接标准[cite: 1]。

## 1. 场景 JSON

* **提供人**：李梦瑶[cite: 1]
* **接收人**：段振阳[cite: 1]
* **格式**：
{
  "case_id": "CASE_001",
  "title": "R2 到 R3 接口关闭",
  "topology_id": "TOPOLOGY_001",
  "source_ip": "192.168.1.10",
  "destination_ip": "192.168.3.10",
  "vendor": "huawei_vrp",
  "ground_truth": {
    "fault_device": "R2",
    "fault_type": "INTERFACE_DOWN",
    "fault_interface": "GigabitEthernet0/0/1"
  }
}

## 2. Parser JSON

* **提供人**：邓予钦[cite: 1]
* **接收人**：段振阳[cite: 1]
* **用途**：把 CLI 原始文本变成结构化 Facts[cite: 1]
* **格式**：
{
  "success": true,
  "device": "R2",
  "vendor": "huawei_vrp",
  "command_type": "DISPLAY_INTERFACE",
  "facts": {
    "interface": "GigabitEthernet0/0/1",
    "physical_status": "DOWN",
    "protocol_status": "DOWN"
  },
  "error": null
}

## 3. Agent 动作 JSON

* **提供人**：段振阳[cite: 1]
* **接收人**：Tool Server[cite: 1]
* **用途**：说明下一步检查什么[cite: 1]
* **格式**：
{
  "action": "CHECK_INTERFACE",
  "target_device": "R2",
  "parameters": {
    "interface": "GigabitEthernet0/0/1"
  },
  "reason": "tracert 在 R2 后中断"
}

## 4. 最终诊断 JSON

* **提供人**：段振阳[cite: 1]
* **接收人**：李梦瑶、评测程序[cite: 1]
* **格式**：
{
  "case_id": "CASE_001",
  "diagnosis_status": "COMPLETED",
  "fault_device": "R2",
  "fault_type": "INTERFACE_DOWN",
  "fault_interface": "GigabitEthernet0/0/1",
  "required_evidence": [
    "ping 100% 丢包",
    "tracert 最后可达 R2",
    "R2 目标路由存在",
    "R2 出接口 physical_status 为 DOWN"
  ]
}

V1 的命令类型和核心 `facts` 字段如下：

| command_type | 核心 facts |
|---|---|
| `PING` | `reachable`、`packet_loss` |
| `TRACERT` | `hops`、`last_reachable_ip`、`last_reachable_device`、`suspect_device` |
| `DISPLAY_ROUTE` | `route_found`、`destination`、`next_hop`、`out_interface` |
| `DISPLAY_INTERFACE` | `interface`、`physical_status`、`protocol_status` |
| `DISPLAY_ARP` | `entry_found`、`target_ip` |

Parser 无法识别回显时必须返回 `success: false`、空 `facts` 和非空 `error`。Agent 收到这种结果后返回 `NEED_MORE_DATA`，不能把解析失败当成路由、接口或 ARP 故障。

## 5. V1 命名约定

以下字段名和取值是 V1 的统一接口，scenario、parser、agent、评测文件必须遵守。

### 5.1 接口名称

程序字段统一使用华为接口全称，例如：

```text
GigabitEthernet0/0/1
```

不使用 `GE0/0/1` 作为结构化数据中的接口值。若原始 CLI 回显使用缩写，由 Parser 负责归一化为全称。

### 5.2 结构化事实字段

```text
route_found
entry_found
physical_status
protocol_status
```

接口状态取值统一为 `UP` 或 `DOWN`。ARP 是否存在统一使用 `entry_found`，不使用 `arp_entry_found`。

### 5.3 Agent 动作字段位置

目标设备统一放在 Agent 动作顶层的 `target_device` 字段中。动作自身需要的输入放在 `parameters` 中。

例如，检查 R2 的指定接口时：

```json
{
  "action": "CHECK_INTERFACE",
  "target_device": "R2",
  "parameters": {
    "interface": "GigabitEthernet0/0/1"
  }
}
```

`action_catalog.json` 使用 `target_device_required` 表示动作是否必须指定设备；`required_parameters` 只列出 `parameters` 内部的必填字段。

### 5.4 诊断结果的附加定位字段

最终诊断保留第 4 节中的通用字段。特定故障类型还可以附带以下字段：

```text
ROUTE_MISSING          -> target_network
ARP_UNRESOLVED         -> target_ip
NEXT_HOP_UNREACHABLE   -> next_hop
```

这些字段用于补充定位对象，不替代 `fault_device`、`fault_type` 和 `fault_interface`。没有适用接口时，`fault_interface` 使用 `null`。
