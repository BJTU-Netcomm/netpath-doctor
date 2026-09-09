from __future__ import annotations

import json
import unittest
from pathlib import Path

from agent.action_schema import AgentAction, validate_action


REPO_ROOT = Path(__file__).resolve().parents[1]


class AgentActionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        catalog_path = REPO_ROOT / "rules" / "action_catalog.json"
        cls.catalog = json.loads(catalog_path.read_text(encoding="utf-8"))

    def test_to_dict_matches_data_contract(self) -> None:
        action = AgentAction(
            action="CHECK_INTERFACE",
            target_device="R2",
            parameters={"interface": "GigabitEthernet0/0/1"},
            reason="tracert 在 R2 后中断",
        )

        self.assertEqual(
            action.to_dict(),
            {
                "action": "CHECK_INTERFACE",
                "target_device": "R2",
                "parameters": {"interface": "GigabitEthernet0/0/1"},
                "reason": "tracert 在 R2 后中断",
            },
        )

    def test_valid_action_passes_validation(self) -> None:
        action = AgentAction(
            action="CHECK_INTERFACE",
            target_device="R2",
            parameters={"interface": "GigabitEthernet0/0/1"},
        )

        validate_action(action, self.catalog)

    def test_unknown_action_is_rejected(self) -> None:
        action = AgentAction(action="SHUTDOWN_INTERFACE")

        with self.assertRaisesRegex(ValueError, "Unknown action"):
            validate_action(action, self.catalog)

    def test_missing_target_device_is_rejected(self) -> None:
        action = AgentAction(
            action="CHECK_INTERFACE",
            parameters={"interface": "GigabitEthernet0/0/1"},
        )

        with self.assertRaisesRegex(ValueError, "target_device"):
            validate_action(action, self.catalog)

    def test_empty_required_parameter_is_rejected(self) -> None:
        action = AgentAction(
            action="CHECK_INTERFACE",
            target_device="R2",
            parameters={"interface": ""},
        )

        with self.assertRaisesRegex(ValueError, "interface"):
            validate_action(action, self.catalog)

    def test_non_read_only_catalog_entry_is_rejected(self) -> None:
        unsafe_catalog = {
            "actions": {
                "CHANGE_CONFIG": {
                    "required_parameters": [],
                    "read_only": False,
                }
            }
        }
        action = AgentAction(action="CHANGE_CONFIG")

        with self.assertRaisesRegex(ValueError, "not read-only"):
            validate_action(action, unsafe_catalog)


if __name__ == "__main__":
    unittest.main()
