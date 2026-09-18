"""Regression tests for prices being misclassified as money claims.

Run with python -m unittest test_claim_parsing.py; no network or httpx needed.
"""
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


with patch.dict(sys.modules, {"httpx": types.ModuleType("httpx")}):
    spec = importlib.util.spec_from_file_location(
        "claim_intel", Path(__file__).with_name("intel.py")
    )
    intel = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(intel)


class ClaimParsingTests(unittest.TestCase):
    def test_question_about_a_price_is_not_income(self):
        self.assertIsNone(intel._parse_claim({
            "text": "Who decides whether they like it enough to pay the $100?"
        }))

    def test_service_cost_before_zero_earned_is_not_income(self):
        self.assertIsNone(intel._parse_claim({
            "text": "The API costs $0.01. My report is pending; USDC earned: $0.00."
        }))

    def test_formal_trophy_claim_is_preserved(self):
        amount, description, formal = intel._parse_claim({
            "text": "🏆 +$0.10 — completed task"
        })
        self.assertEqual((amount, description, formal),
                         (0.10, "completed task", True))

    def test_trophy_tally_fallback_is_preserved(self):
        result = intel._parse_claim({"text": "🏆 tally: about $9,360 earned"})
        self.assertEqual(result[0], 9360.0)
        self.assertFalse(result[2])


if __name__ == "__main__":
    unittest.main()
