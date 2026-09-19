from __future__ import annotations

import unittest

from benchmarks.live_preflight import probe_transport


class FakeTransport:
    def __init__(self) -> None:
        self.devices = {"R2": {}, "R1": {}, "R3": {}}

    def send(self, device: str, command: str) -> str:
        self.last_command = command
        if device == "R2":
            raise TimeoutError("connection timed out")
        return f"Huawei Versatile Routing Platform on {device}"


class LivePreflightTests(unittest.TestCase):
    def test_reports_each_device_and_continues_after_failure(self) -> None:
        result = probe_transport(FakeTransport())  # type: ignore[arg-type]

        self.assertEqual(result["total"], 3)
        self.assertEqual(result["reachable"], 2)
        self.assertEqual(result["failed"], 1)
        self.assertFalse(result["all_reachable"])
        self.assertEqual(
            [device["device"] for device in result["devices"]],
            ["R1", "R2", "R3"],
        )
        self.assertIn("TimeoutError", result["devices"][1]["error"])


if __name__ == "__main__":
    unittest.main()
