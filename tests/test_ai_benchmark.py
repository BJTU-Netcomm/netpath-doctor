from benchmarks.ai_benchmark import run_benchmark


def test_ai_tool_contract_benchmark_passes_all_golden_cases():
    report = run_benchmark()
    assert report["planner"] == "deterministic_scripted_planner"
    assert report["model_accuracy_claim"] is False
    assert report["total"] == 20
    assert report["all_passed"] is True
    assert all(case["replay_refs"] == case["successful_observations"] for case in report["cases"])
