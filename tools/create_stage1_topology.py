"""Create a stable eNSP stage-1 topology without the management Cloud links.

The current lab connects the same Host-Only adapter to three Cloud ports.  On
the installed eNSP version this makes the management links flap and can freeze
the GUI while saving.  Stage 1 keeps only the two router-to-router links so the
business configuration can be saved before the management network is added
through a layer-2 switch.
"""

from pathlib import Path
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "topologies" / "ensp" / "netpath-doctor-r1-r2-r3.topo"
TARGET = ROOT / "topologies" / "ensp" / "netpath-doctor-r1-r2-r3-stage1-no-cloud.topo"
CLOUD_ID = "81D98E98-E4D9-4A7D-AE59-37BF55301504"


def main() -> None:
    # eNSP 1.3 writes ASCII/UTF-8 bytes while declaring the legacy encoding
    # name "UNICODE", which Python's XML parser does not recognize.  Normalize
    # the declaration only in memory, then restore eNSP's declaration on disk.
    source_text = SOURCE.read_text(encoding="utf-8")
    normalized = source_text.replace('encoding="UNICODE"', 'encoding="utf-8"', 1)
    root = ET.fromstring(normalized)
    tree = ET.ElementTree(root)

    devices = root.find("devices")
    if devices is None:
        raise RuntimeError("Topology has no <devices> element")
    for device in list(devices):
        if device.get("id") == CLOUD_ID:
            devices.remove(device)

    lines = root.find("lines")
    if lines is None:
        raise RuntimeError("Topology has no <lines> element")
    for line in list(lines):
        if CLOUD_ID in {line.get("srcDeviceID"), line.get("destDeviceID")}:
            lines.remove(line)

    tips = root.find("txttips")
    if tips is not None:
        for tip in list(tips):
            if "management" in tip.get("content", "").lower():
                tips.remove(tip)

    ET.indent(tree, space="    ")
    xml_bytes = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    xml_text = xml_bytes.decode("utf-8").replace(
        "encoding='utf-8'", 'encoding="UNICODE"', 1
    )
    TARGET.write_text(xml_text, encoding="utf-8", newline="\r\n")

    # Fail immediately if the generated topology is malformed.
    check_text = TARGET.read_text(encoding="utf-8").replace(
        'encoding="UNICODE"', 'encoding="utf-8"', 1
    )
    check = ET.fromstring(check_text)
    device_names = {d.get("name") for d in check.find("devices", [])}
    remaining_lines = list(check.find("lines", []))
    if device_names != {"R1", "R2", "R3"} or len(remaining_lines) != 2:
        raise RuntimeError(
            f"Unexpected stage-1 topology: devices={device_names}, "
            f"lines={len(remaining_lines)}"
        )

    print(TARGET)


if __name__ == "__main__":
    main()
