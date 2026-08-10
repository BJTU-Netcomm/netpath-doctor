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
