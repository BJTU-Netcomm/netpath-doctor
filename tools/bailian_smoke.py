"""Smoke-test Bailian access and tool calling without exposing the API key."""

from __future__ import annotations

import json
import sys

# Support both `python -m tools.bailian_smoke` and direct execution.
if __package__ in (None, ""):
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai.bailian_client import BailianClient, run_tool_call_smoke_test


def main() -> int:
    try:
        result = run_tool_call_smoke_test(BailianClient())
    except RuntimeError as exc:
        print(f"Bailian smoke test failed: {exc}", file=sys.stderr)
        return 2

    message = result.get("choices", [{}])[0].get("message", {})
    calls = message.get("tool_calls") or []
    summary = {
        "model": result.get("model"),
        "tool_call_count": len(calls),
        "tool_calls": [
            {
                "name": call.get("function", {}).get("name"),
                "arguments": call.get("function", {}).get("arguments"),
            }
            for call in calls
        ],
        "content_present": bool(message.get("content")),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if calls else 1


if __name__ == "__main__":
    raise SystemExit(main())
