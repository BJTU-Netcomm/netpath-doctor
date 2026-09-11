# Parser 字段清单

## 五类命令核心提取字段

### PING
- reachable (true/false)
- packet_loss (数值，0-100)

### TRACERT
- hops (逐跳 IP/超时记录)
- last_reachable_ip (最后一个可达 IP)
- last_reachable_device (通过 IP 映射得到的设备名，可选)
- suspect_device (疑似故障设备，可选)

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
    "error": null 或错误字符串
}

## 错误类型
- SUCCESS
- EMPTY_OUTPUT
- COMMAND_FAILED
- UNSUPPORTED_COMMAND
- UNSUPPORTED_VENDOR
- INCOMPLETE_OUTPUT
- PARSE_FAILED
