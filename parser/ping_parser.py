from parser.huawei_vrp import parse_cli_output


def parse_ping(raw_text: str, device: str) -> dict:
    return parse_cli_output("PING", raw_text, device=device)
