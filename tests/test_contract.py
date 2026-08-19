from __future__ import annotations

import json
import unittest
from pathlib import Path

from orchestra_display import RobotState


class ContractTest(unittest.TestCase):
    def test_python_states_match_public_contract(self) -> None:
        contract_path = Path(__file__).parents[1] / "contract" / "states.json"
        contract = json.loads(contract_path.read_text())
        contract_codes = [item["code"] for item in contract["states"]]
        self.assertEqual(contract_codes, [state.value for state in RobotState])


if __name__ == "__main__":
    unittest.main()
