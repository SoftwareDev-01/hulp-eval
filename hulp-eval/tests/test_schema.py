"""
Schema validation tests — verifies the brief_schema.json is correct
and tests edge cases for the schema grader.

Run with: pytest tests/test_schema.py -v
"""

import json
import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from graders.schema_grader import grade_schema


@pytest.fixture
def schema():
    schema_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "schema", "brief_schema.json"
    )
    with open(schema_path, "r") as f:
        return json.load(f)


# ─── Valid outputs ────────────────────────────────────────────────────────────

def test_valid_complete_output(schema):
    """A complete, valid output should pass schema validation."""
    output = json.dumps({
        "intent": "transport_booking",
        "brief": "Client needs a cab for Rahul tomorrow at 6:30 am.",
        "facts": [
            {"text": "traveller is Rahul", "source_ids": ["m1"]},
            {"text": "pickup at DLF Phase 1", "source_ids": ["m1"]},
        ],
        "hard_constraints": ["pickup at 06:30 IST"],
        "preferences": [],
        "missing_information": ["exact pickup address"],
        "clarification_questions": ["What is the exact pickup address?"],
        "risk_flags": [],
        "confidence": "high",
    })
    result = grade_schema(output, schema)
    assert result["valid"] is True
    assert result["parsed"] is not None


def test_valid_with_markdown_fences(schema):
    """Output wrapped in markdown fences should still parse."""
    output = '```json\n' + json.dumps({
        "intent": "test",
        "brief": "test brief",
        "facts": [],
        "hard_constraints": [],
        "preferences": [],
        "missing_information": [],
        "clarification_questions": [],
        "risk_flags": [],
        "confidence": "medium",
    }) + '\n```'
    result = grade_schema(output, schema)
    assert result["valid"] is True


# ─── Invalid outputs ─────────────────────────────────────────────────────────

def test_invalid_not_json(schema):
    """Plain text should fail."""
    result = grade_schema("This is not JSON at all.", schema)
    assert result["valid"] is False
    assert "not valid JSON" in result["error"]


def test_invalid_missing_required_field(schema):
    """Missing a required field should fail."""
    output = json.dumps({
        "intent": "test",
        "brief": "test",
        # Missing: facts, hard_constraints, etc.
    })
    result = grade_schema(output, schema)
    assert result["valid"] is False


def test_invalid_wrong_confidence_value(schema):
    """Confidence must be high/medium/low."""
    output = json.dumps({
        "intent": "test",
        "brief": "test",
        "facts": [],
        "hard_constraints": [],
        "preferences": [],
        "missing_information": [],
        "clarification_questions": [],
        "risk_flags": [],
        "confidence": "very_high",  # invalid
    })
    result = grade_schema(output, schema)
    assert result["valid"] is False


def test_invalid_facts_missing_source_ids(schema):
    """Facts without source_ids should fail."""
    output = json.dumps({
        "intent": "test",
        "brief": "test",
        "facts": [{"text": "some fact"}],  # missing source_ids
        "hard_constraints": [],
        "preferences": [],
        "missing_information": [],
        "clarification_questions": [],
        "risk_flags": [],
        "confidence": "low",
    })
    result = grade_schema(output, schema)
    assert result["valid"] is False
