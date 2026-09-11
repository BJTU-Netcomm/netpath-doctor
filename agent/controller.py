from __future__ import annotations

import json
from pathlib import Path

from agent.command_mapper import load_action_catalog
from agent.state_machine import DiagnosisStateMachine
from tool_server.mock_executor import MockExecutor
from tool_server.replay_executor import ReplayExecutor


class NetPathDoctorController:
    def __init__(self, repo_root: str | Path):
        self.repo_root = Path(repo_root)
        self.action_catalog = load_action_catalog(self.repo_root / "rules" / "action_catalog.json")
        self.state_machine = DiagnosisStateMachine()

    def run_scenario(self, scenario_path: str | Path) -> dict:
        scenario_path = Path(scenario_path)
        scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
        return self.run_scenario_data(scenario, scenario_path.parent)

    def run_scenario_data(
        self,
        scenario: dict,
        case_dir: str | Path,
    ) -> dict:
        scenario = dict(scenario)
        scenario.pop("ground_truth", None)
        case_dir = Path(case_dir)

        if (case_dir / "log_manifest.json").exists():
            executor = ReplayExecutor(scenario, self.action_catalog, case_dir)
        else:
            mock_path = case_dir / "mock_outputs.json"
            if mock_path.exists():
                scenario["mock_outputs"] = json.loads(mock_path.read_text(encoding="utf-8"))
            executor = MockExecutor(scenario, self.action_catalog)
        return self.state_machine.run(scenario, executor)
