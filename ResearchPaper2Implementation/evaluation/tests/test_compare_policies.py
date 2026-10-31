import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluation.compare_policies import classify_transition
from evaluation.policy_check import NOT_SATISFIED, SATISFIED


class ComparePoliciesTests(unittest.TestCase):
    def test_all_four_transitions_are_preserved(self):
        self.assertEqual(classify_transition(SATISFIED, SATISFIED), "stable_satisfied")
        self.assertEqual(classify_transition(NOT_SATISFIED, SATISFIED), "gap_closed")
        self.assertEqual(classify_transition(NOT_SATISFIED, NOT_SATISFIED), "persistent_gap")
        self.assertEqual(classify_transition(SATISFIED, NOT_SATISFIED), "regression")


if __name__ == "__main__":
    unittest.main()
