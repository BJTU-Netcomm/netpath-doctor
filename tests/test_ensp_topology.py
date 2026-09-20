from __future__ import annotations

import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
TOPOLOGY_PATH = (
    REPO_ROOT / "topologies" / "ensp" / "netpath-doctor-r1-r2-r3.topo"
)


class ENSPTopologyTests(unittest.TestCase):
    def setUp(self) -> None:
        # eNSP 1.3 emits a UTF-8 file with the legacy declaration
        # encoding="UNICODE"; normalize that declaration for Python's parser.
        content = TOPOLOGY_PATH.read_text(encoding="utf-8").replace(
            'encoding="UNICODE"', 'encoding="utf-8"', 1
        )
        self.root = ET.fromstring(content)

    def test_contains_expected_devices(self) -> None:
        devices = {
            device.attrib["name"]: device.attrib["model"]
            for device in self.root.findall("./devices/dev")
        }

        self.assertEqual(
            devices,
            {
                "R1": "AR2220",
                "R2": "AR2220",
                "R3": "AR2220",
                "MGMT_CLOUD": "Cloud",
            },
        )

    def test_business_and_management_ports_are_wired_once(self) -> None:
        device_names = {
            device.attrib["id"]: device.attrib["name"]
            for device in self.root.findall("./devices/dev")
        }
        links = []
        for line in self.root.findall("./lines/line"):
            pair = line.find("interfacePair")
            self.assertIsNotNone(pair)
            links.append(
                (
                    device_names[line.attrib["srcDeviceID"]],
                    int(pair.attrib["srcIndex"]),  # type: ignore[union-attr]
                    device_names[line.attrib["destDeviceID"]],
                    int(pair.attrib["tarIndex"]),  # type: ignore[union-attr]
                )
            )

        self.assertEqual(
            links,
            [
                ("R1", 0, "R2", 0),
                ("R2", 1, "R3", 0),
                ("R1", 2, "MGMT_CLOUD", 0),
                ("R2", 2, "MGMT_CLOUD", 1),
                ("R3", 2, "MGMT_CLOUD", 2),
            ],
        )

    def test_cloud_binding_remains_machine_local(self) -> None:
        cloud = self.root.find("./devices/dev[@name='MGMT_CLOUD']")
        self.assertIsNotNone(cloud)
        adapter_ids = {
            mapping.attrib["adapterUid"]
            for mapping in cloud.findall("./slot/interfaceMap")  # type: ignore[union-attr]
        }

        self.assertTrue(
            all(adapter_id == "" or adapter_id.startswith("\\Device\\NPF_") for adapter_id in adapter_ids)
        )


if __name__ == "__main__":
    unittest.main()
