from parser.huawei_vrp import parse_cli_output


def parse_route(raw_text: str, device: str) -> dict:
    return parse_cli_output("DISPLAY_ROUTE", raw_text, device=device)
