from __future__ import annotations

import unittest
from pathlib import Path

from benchmarks.runner import run_benchmark


REPO_ROOT = Path(__file__).resolve().parents[1]


class BenchmarkTests(unittest.TestCase):
    def test_all_golden_cases_pass(self) -> None:
        report = run_benchmark(REPO_ROOT)

        self.assertEqual(report["total"], 20)
        self.assertEqual(report["passed"], 20)
        self.assertTrue(report["all_passed"])
        self.assertEqual(report["pass_rate"], 1.0)
        self.assertEqual(report["execution_modes"], {"cli_replay": 20})
        case_001 = next(case for case in report["cases"] if case["case_id"] == "CASE_001")
        self.assertEqual(case_001["execution_mode"], "cli_replay")
        for case in report["cases"]:
            self.assertEqual(case["actual"]["case_id"], case["case_id"])

        case_010 = next(case for case in report["cases"] if case["case_id"] == "CASE_010")
        self.assertEqual(
            case_010["actual"]["action_trace"][0]["parameters"]["target_ip"],
            "192.168.3.11",
        )


if __name__ == "__main__":
    unittest.main()
