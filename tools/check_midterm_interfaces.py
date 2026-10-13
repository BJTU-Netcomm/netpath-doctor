"""Offline acceptance for the three measured interface captures; never connects to devices."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from parser.huawei_vrp import parse_cli_output

REQUIRED = (
    ("normal/interface_detail_R2.txt", "UP"),
    ("interface_down/interface_detail_R2_down.txt", "DOWN"),
    ("recovered/interface_detail_R2_recovered.txt", "UP"),
)


def check(records_root: Path) -> dict:
    results = []
    for filename, expected in REQUIRED:
        path = records_root / filename
        row = {"file": filename, "expected_physical": expected,
               "expected_protocol": expected, "passed": False}
        if not path.is_file():
            row.update(status="MISSING", error="Measured capture has not been supplied")
        else:
            try:
                raw = path.read_bytes()
                parsed = parse_cli_output("CHECK_INTERFACE", raw.decode("utf-8-sig"), device="R2")
                facts = parsed.get("facts", {})
                row.update(sha256=hashlib.sha256(raw).hexdigest(), parsed=parsed)
                row["passed"] = parsed["success"] is True and all((
                    facts.get("interface") == "GigabitEthernet0/0/1",
                    facts.get("physical_status") == expected,
                    facts.get("protocol_status") == expected,
                ))
                row["status"] = "PASS" if row["passed"] else "FAIL"
            except (OSError, UnicodeError) as exc:
                row.update(status="FAIL", error=str(exc))
        results.append(row)
    return {"scope": "offline interface capture checks; provenance must be reviewed by collector",
            "all_passed": all(r["passed"] for r in results), "results": results}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--records-root", type=Path, default=ROOT / "docs/cli_records")
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()
    result = check(args.records_root)
    body = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(body + "\n", encoding="utf-8")
    print(body)
    if result["all_passed"]:
        return 0
    return 2 if any(r["status"] == "MISSING" for r in result["results"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
