from __future__ import annotations

import re
from typing import Any, Callable


ACTION_TO_COMMAND_TYPE = {
    "RUN_PING": "PING",
    "RUN_TRACERT": "TRACERT",
    "CHECK_ROUTE": "DISPLAY_ROUTE",
    "CHECK_INTERFACE": "DISPLAY_INTERFACE",
    "CHECK_ARP": "DISPLAY_ARP",
}
SUPPORTED_VENDORS = {"huawei_vrp"}


def normalize_interface(name: str) -> str:
    name = name.strip()
    match = re.fullmatch(r"GE(\d+(?:/\d+)+)", name, flags=re.IGNORECASE)
    if match:
        return f"GigabitEthernet{match.group(1)}"
    return name


def parse_ping(text: str, _: dict[str, Any]) -> dict[str, Any]:
    match = re.search(r"([\d.]+)%\s+packet loss", text, flags=re.IGNORECASE)
    if not match:
        raise ValueError("ping output does not contain packet loss")
    loss_value = float(match.group(1))
    packet_loss: int | float = int(loss_value) if loss_value.is_integer() else loss_value
    return {"reachable": loss_value < 100, "packet_loss": packet_loss}


def parse_tracert(text: str, context: dict[str, Any]) -> dict[str, Any]:
    hops: list[dict[str, Any]] = []
    for line in text.splitlines():
        match = re.match(r"\s*(\d+)\s+(.+)$", line)
        if not match:
            continue
        hop = int(match.group(1))
        remainder = match.group(2)
        ip_match = re.search(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", remainder)
        hops.append({"hop": hop, "ip": ip_match.group(0) if ip_match else None})

    if not hops:
        raise ValueError("tracert output does not contain recognizable hops")

    reachable_hops = [hop for hop in hops if hop["ip"]]
    if not reachable_hops:
        return {"hops": hops, "last_reachable_ip": None}

    last_ip = reachable_hops[-1]["ip"]
    facts: dict[str, Any] = {"hops": hops, "last_reachable_ip": last_ip}
    device = context.get("ip_to_device", {}).get(last_ip)
    if device:
        facts["last_reachable_device"] = device
        facts["suspect_device"] = device
    return facts


def parse_route(text: str, _: dict[str, Any]) -> dict[str, Any]:
    summary_match = re.search(r"Summary Count\s*:\s*(\d+)", text, flags=re.IGNORECASE)
    if summary_match and int(summary_match.group(1)) == 0:
        return {"route_found": False}

    route_pattern = re.compile(
        r"^\s*(?P<destination>(?:\d{1,3}\.){3}\d{1,3}/\d+)\s+"
        r"\S+\s+\d+\s+\d+\s+\S+\s+"
        r"(?P<next_hop>(?:\d{1,3}\.){3}\d{1,3})\s+"
        r"(?P<interface>\S+)\s*$"
    )
    for line in text.splitlines():
        match = route_pattern.match(line)
        if match:
            return {
                "route_found": True,
                "destination": match.group("destination"),
                "next_hop": match.group("next_hop"),
                "out_interface": normalize_interface(match.group("interface")),
            }
    raise ValueError("route output does not contain a recognizable route entry")


def parse_interface(text: str, _: dict[str, Any]) -> dict[str, Any]:
    physical = re.search(r"^\s*(\S+)\s+current state\s*:\s*(UP|DOWN)", text, flags=re.I | re.M)
    protocol = re.search(r"^\s*Line protocol current state\s*:\s*(UP|DOWN)", text, flags=re.I | re.M)
    if not physical or not protocol:
        raise ValueError("interface output does not contain physical and protocol states")
    return {
        "interface": normalize_interface(physical.group(1)),
        "physical_status": physical.group(2).upper(),
        "protocol_status": protocol.group(1).upper(),
    }


def parse_arp(text: str, context: dict[str, Any]) -> dict[str, Any]:
    target_ip = context.get("target_ip")
    if not target_ip:
        raise ValueError("target_ip is required to parse ARP output")
    entry_pattern = re.compile(rf"^\s*{re.escape(target_ip)}\s+\S+", flags=re.MULTILINE)
    if entry_pattern.search(text):
        return {"entry_found": True, "target_ip": target_ip}
    if re.search(r"\bTotal\s*:\s*0\b", text, flags=re.IGNORECASE):
        return {"entry_found": False, "target_ip": target_ip}
    raise ValueError("ARP output does not contain an entry or a zero-entry summary")


PARSERS: dict[str, Callable[[str, dict[str, Any]], dict[str, Any]]] = {
    "RUN_PING": parse_ping,
    "PING": parse_ping,
    "RUN_TRACERT": parse_tracert,
    "TRACERT": parse_tracert,
    "CHECK_ROUTE": parse_route,
    "DISPLAY_ROUTE": parse_route,
    "CHECK_INTERFACE": parse_interface,
    "DISPLAY_INTERFACE": parse_interface,
    "CHECK_ARP": parse_arp,
    "DISPLAY_ARP": parse_arp,
}


def parse_cli_output(
    command_type: str,
    text: str,
    *,
    device: str | None = None,
    vendor: str = "huawei_vrp",
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    parser = PARSERS.get(command_type)
    canonical_type = ACTION_TO_COMMAND_TYPE.get(command_type, command_type)
    if vendor not in SUPPORTED_VENDORS:
        return {
            "success": False,
            "device": device,
            "vendor": vendor,
            "command_type": canonical_type,
            "facts": {},
            "error": f"Unsupported vendor: {vendor}",
        }
    if parser is None:
        return {
            "success": False,
            "device": device,
            "vendor": vendor,
            "command_type": canonical_type,
            "facts": {},
            "error": f"Unsupported command type: {command_type}",
        }

    if not text or not text.strip():
        return {
            "success": False,
            "device": device,
            "vendor": vendor,
            "command_type": canonical_type,
            "facts": {},
            "error": "EMPTY_OUTPUT",
        }

    try:
        facts = parser(text, context or {})
    except ValueError as exc:
        return {
            "success": False,
            "device": device,
            "vendor": vendor,
            "command_type": canonical_type,
            "facts": {},
            "error": str(exc),
        }

    return {
        "success": True,
        "device": device,
        "vendor": vendor,
        "command_type": canonical_type,
        "facts": facts,
        "error": None,
    }
