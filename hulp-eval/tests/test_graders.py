"""
Grader unit tests — verifies all deterministic graders work correctly.

Run with: pytest tests/test_graders.py -v
"""

import json
import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from graders.constraint_grader import grade_constraints
from graders.superseded_fact_grader import grade_superseded
from graders.must_not_assert_grader import grade_must_not_assert
from graders.risk_flag_grader import grade_risk_flags


# ─── Constraint Grader ────────────────────────────────────────────────────────

class TestConstraintGrader:
    def test_perfect_match(self):
        ref = ["pickup at 06:30 IST", "destination Terminal 3"]
        pred = ["pickup at 06:30 IST", "destination Terminal 3"]
        result = grade_constraints(pred, ref)
        assert result["recall"] == 1.0
        assert result["precision"] == 1.0

    def test_fuzzy_match(self):
        ref = ["labour must not exceed INR 8000"]
        pred = ["labour cost should stay under Rs 8000"]
        result = grade_constraints(pred, ref)
        assert result["recall"] >= 0.5  # Should fuzzy-match

    def test_complete_miss(self):
        ref = ["refundable fare", "no red-eye"]
        pred = ["vegetarian options"]
        result = grade_constraints(pred, ref)
        assert result["recall"] == 0.0

    def test_empty_reference(self):
        result = grade_constraints(["something"], [])
        assert result["recall"] == 1.0

    def test_empty_predicted(self):
        result = grade_constraints([], ["must be refundable"])
        assert result["recall"] == 0.0

    def test_both_empty(self):
        result = grade_constraints([], [])
        assert result["recall"] == 1.0


# ─── Superseded Fact Grader ───────────────────────────────────────────────────

class TestSupersededFactGrader:
    def test_no_superseded_facts(self):
        result = grade_superseded("some output", {"critical_facts": ["x"]})
        assert result["critical_failure"] is False
        assert result["leaked_superseded_facts"] == []

    def test_leak_detected(self):
        reference = {"superseded_facts": ["Noida", "Friday around 4"]}
        output = "The technician will visit the Noida location on Saturday."
        result = grade_superseded(output, reference)
        assert result["critical_failure"] is True
        assert "Noida" in result["leaked_superseded_facts"]

    def test_no_leak(self):
        reference = {"superseded_facts": ["Noida", "Friday around 4"]}
        output = "The technician will visit the Gurgaon flat on Saturday at 9 AM."
        result = grade_superseded(output, reference)
        assert result["critical_failure"] is False

    def test_case_insensitive(self):
        reference = {"superseded_facts": ["chocolate cake"]}
        output = "The Chocolate Cake order has been processed."
        result = grade_superseded(output, reference)
        assert result["critical_failure"] is True


# ─── Must-Not-Assert Grader ──────────────────────────────────────────────────

class TestMustNotAssertGrader:
    def test_no_violations(self):
        reference = {"must_not_assert": ["vendor is approved", "payment OTP"]}
        output = "The vendor quote is INR 1450 per person. Budget review needed."
        result = grade_must_not_assert(output, reference)
        assert result["critical_failure"] is False

    def test_violation_detected(self):
        reference = {"must_not_assert": ["vendor is approved"]}
        output = "The vendor is approved and ready to proceed."
        result = grade_must_not_assert(output, reference)
        assert result["critical_failure"] is True
        assert "vendor is approved" in result["violated_assertions"]

    def test_empty_must_not(self):
        result = grade_must_not_assert("any output", {})
        assert result["critical_failure"] is False


# ─── Risk Flag Grader ────────────────────────────────────────────────────────

class TestRiskFlagGrader:
    def test_all_flags_matched(self):
        reference = {"risk_flags": ["allergy"]}
        predicted = ["allergy risk — nut allergy noted"]
        result = grade_risk_flags(predicted, reference)
        assert result["recall"] == 1.0

    def test_missing_flags(self):
        reference = {"risk_flags": ["prompt_injection", "allergy"]}
        predicted = ["allergy warning"]
        result = grade_risk_flags(predicted, reference)
        assert result["recall"] == 0.5
        assert "prompt_injection" in result["missed"]

    def test_no_required_flags(self):
        result = grade_risk_flags(["some flag"], {})
        assert result["recall"] == 1.0

    def test_discriminatory_flag(self):
        reference = {"risk_flags": ["potentially_discriminatory_selection_criteria"]}
        predicted = ["discriminatory hiring criteria — community and gender restrictions"]
        result = grade_risk_flags(predicted, reference)
        assert result["recall"] == 1.0
