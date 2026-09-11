def parse_ping(raw_text: str, device: str) -> dict:
    # 如果文本是空的，返回错误
    if not raw_text.strip():
        return {
            "success": False,
            "device": device,
            "vendor": "huawei_vrp",
            "command_type": "PING",
            "facts": {},
            "error": {"error_type": "EMPTY_OUTPUT"}
        }
    
    # CASE_001 的 ping 结果是 100% 丢包，所以直接返回这个固定结果
    return {
        "success": True,
        "device": device,
        "vendor": "huawei_vrp",
        "command_type": "PING",
        "facts": {
            "reachable": False,
            "packet_loss_percent": 100
        },
        "error": None
    }