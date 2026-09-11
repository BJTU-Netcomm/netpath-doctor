from parser.huawei_vrp import parse_cli_output


def parse_arp(raw_text: str, device: str, target_ip: str | None = None) -> dict:
    return parse_cli_output(
        "DISPLAY_ARP",
        raw_text,
        device=device,
        context={"target_ip": target_ip} if target_ip else None,
    )
