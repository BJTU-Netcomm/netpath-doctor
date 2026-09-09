# Parser 字段清单

## 五类命令核心提取字段

### PING
- reachable (true/false)
- packet_loss_percent (数值)

### TRACERT
- last_reachable_hop (设备名或IP)
- timeout_hop (超时跳数)

### DISPLAY_ROUTE
- route_found (true/false)

### DISPLAY_INTERFACE
- interface (接口全称，如 GigabitEthernet0/0/1)
- physical_status (UP/DOWN)
- protocol_status (UP/DOWN)

### DISPLAY_ARP
- entry_found (true/false)

## Parser 统一外壳格式
{
    "success": true/false,
    "device": "设备名",
    "vendor": "huawei_vrp",
    "command_type": "命令类型",
    "facts": { 提取的核心字段 },
    "error": null 或 { "error_type": "错误代码" }
}

## 错误类型
- SUCCESS
- EMPTY_OUTPUT
- COMMAND_FAILED
- UNSUPPORTED_COMMAND
- UNSUPPORTED_VENDOR
- INCOMPLETE_OUTPUT
- PARSE_FAILED