from parser.huawei_vrp import parse_cli_output


def parse_tracert(raw_text: str, device: str, context: dict | None = None) -> dict:
    return parse_cli_output("TRACERT", raw_text, device=device, context=context)
