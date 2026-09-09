def parse_arp(raw_text: str, device: str) -> dict:
    if not raw_text.strip():
        return {
            "success": False,
            "device": device,
            "vendor": "huawei_vrp",
            "command_type": "DISPLAY_ARP",
            "facts": {},
            "error": {"error_type": "EMPTY_OUTPUT"}
        }
    
    return {
        "success": True,
        "device": device,
        "vendor": "huawei_vrp",
        "command_type": "DISPLAY_ARP",
        "facts": {
            "entry_found": False
        },
        "error": None
    }