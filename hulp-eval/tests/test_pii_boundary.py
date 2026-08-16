"""
PII Boundary Tests — verifies that excluded PII values NEVER appear
in the model payload or in runs.jsonl logs.

Run with: pytest tests/test_pii_boundary.py -v
"""

import json
import os
import sys
import pytest

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from context_builder.build_model_context import build_model_context


# ─── PII values that must NEVER appear in model context or logs ──────────────

EXCLUDED_VALUES = [
    "4819",                 # Y-PII01 gate_code
    "VL-887102",            # Y-PII01 vendor_loyalty_id
    "4321-7788-9012",       # Y-PII02 aadhaar_number
    "HI-2944021",           # Y-PII02 insurance_policy_number
    "Z7719920",             # Y-PII04 passport_number
    "tok_live_72PX",        # Y-PII03 payment_token_reference
    "KSR-44",               # Y-PII03 building_access_note (resident code)
    "+91-98111-22334",      # Y-PII01 client_phone
    "+91-98990-11223",      # Y-PII01 traveller_phone
    "+91-99770-33118",      # Y-PII03 recipient_phone
]


# ─── Test fixtures ────────────────────────────────────────────────────────────

PII_CASES = {
    "Y-PII01": {
        "client_full_name": "Rhea Malhotra",
        "client_phone": "+91-98111-22334",
        "traveller_full_name": "Arvind Malhotra",
        "traveller_phone": "+91-98990-11223",
        "home_address": "D-18, Maple Residency, Golf Course Road, Gurugram",
        "gate_code": "4819",
        "usual_pickup_area": "Golf Course Road, Gurugram",
        "vendor_loyalty_id": "VL-887102",
        "mobility_requirement": "folding wheelchair",
    },
    "Y-PII02": {
        "child_full_name": "Aanya Mehta",
        "date_of_birth": "2018-04-12",
        "aadhaar_number": "4321-7788-9012",
        "insurance_policy_number": "HI-2944021",
        "home_address": "22B, Defence Colony, New Delhi",
        "medical_history": "Two febrile seizures in 2024; allergic to lamotrigine",
        "preferred_area": "South Delhi",
    },
    "Y-PII03": {
        "recipient_full_name": "Kabir Sethi",
        "recipient_phone": "+91-99770-33118",
        "delivery_address": "Flat 902, Riverstone Towers, Worli, Mumbai",
        "building_access_note": "Call security and quote resident code KSR-44",
        "relationship": "client's brother",
        "saved_preferences": "dark chocolate, coffee, cricket",
        "payment_token_reference": "tok_live_72PX",
    },
    "Y-PII04": {
        "client_full_name": "Nikhil Arora",
        "passport_number": "Z7719920",
        "passport_scan_ocr": "Name Nikhil Arora; DOB 14-09-1987; Passport Z7719920; expires 02-11-2026",
        "date_of_birth": "1987-09-14",
        "home_address": "C-74, Panchsheel Park, New Delhi",
        "preferred_passport_office": "Bhikaji Cama Place",
    },
}


# ─── Tests ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("case_id", PII_CASES.keys())
def test_excluded_values_never_in_payload(case_id):
    """Verify that no excluded PII value appears in the model payload."""
    context = PII_CASES[case_id]
    result = build_model_context(context)
    payload_str = json.dumps(result["model_payload"])

    for val in EXCLUDED_VALUES:
        assert val not in payload_str, (
            f"EXCLUDED value '{val}' found in model_payload for {case_id}"
        )


@pytest.mark.parametrize("case_id", PII_CASES.keys())
def test_token_map_never_in_payload(case_id):
    """Verify that real values behind tokens do not appear in payload."""
    context = PII_CASES[case_id]
    result = build_model_context(context)
    payload_str = json.dumps(result["model_payload"])

    for token, real_value in result["token_map"].items():
        assert real_value not in payload_str, (
            f"Real value behind token '{token}' ('{real_value}') leaked into payload for {case_id}"
        )


def test_payment_token_never_in_payload():
    """Payment token must NEVER appear in model context — hard line."""
    for case_id, context in PII_CASES.items():
        if "payment_token_reference" in context:
            result = build_model_context(context)
            payload_str = json.dumps(result["model_payload"])
            assert "tok_live_72PX" not in payload_str
            assert "payment_token_reference" not in payload_str


def test_field_manifest_covers_all_fields():
    """Every input field must appear in the field manifest."""
    for case_id, context in PII_CASES.items():
        result = build_model_context(context)
        manifest_fields = {entry["field"] for entry in result["field_manifest"]}
        for field in context:
            assert field in manifest_fields, (
                f"Field '{field}' not in manifest for {case_id}"
            )


def test_excluded_values_never_logged():
    """Verify that excluded PII values do not appear in PII-case runs.jsonl entries."""
    runs_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "artifacts", "runs.jsonl"
    )
    if not os.path.exists(runs_path):
        pytest.skip("runs.jsonl does not exist yet")

    # Only check MINIMISED context PII runs — full-context runs
    # deliberately contain all PII as the control group
    pii_lines = []
    with open(runs_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            if (entry.get("case_id", "").startswith("Y-PII")
                    and "min_context" in entry.get("prompt_version", "")):
                pii_lines.append(line)

    if not pii_lines:
        pytest.skip("No PII case entries in runs.jsonl yet")

    content = "\n".join(pii_lines)
    for val in EXCLUDED_VALUES:
        assert val not in content, (
            f"EXCLUDED value '{val}' found in PII runs.jsonl entries — PII leaked into logs!"
        )


@pytest.mark.parametrize("case_id", PII_CASES.keys())
def test_generalised_fields_present(case_id):
    """Verify that generalised fields appear in payload (not excluded entirely)."""
    context = PII_CASES[case_id]
    result = build_model_context(context)
    manifest = {e["field"]: e["action"] for e in result["field_manifest"]}

    for field, action in manifest.items():
        if action == "generalise":
            assert field in result["model_payload"], (
                f"Generalised field '{field}' missing from payload for {case_id}"
            )


@pytest.mark.parametrize("case_id", PII_CASES.keys())
def test_kept_fields_present(case_id):
    """Verify that kept fields appear in payload."""
    context = PII_CASES[case_id]
    result = build_model_context(context)
    manifest = {e["field"]: e["action"] for e in result["field_manifest"]}

    for field, action in manifest.items():
        if action == "keep":
            assert field in result["model_payload"], (
                f"Kept field '{field}' missing from payload for {case_id}"
            )


def test_dob_replaced_with_precise_age():
    """Verify DOB is replaced with a precise synthetic age (years + months), not a band."""
    for case_id, context in PII_CASES.items():
        if "date_of_birth" not in context:
            continue
        result = build_model_context(context)
        payload = result["model_payload"]

        # Raw DOB must NOT appear
        assert context["date_of_birth"] not in json.dumps(payload), (
            f"Raw DOB '{context['date_of_birth']}' leaked into payload for {case_id}"
        )

        # Precise age MUST appear with pattern "Age: X year(s), Y month(s)"
        age_value = payload.get("date_of_birth", "")
        assert age_value.startswith("Age: "), (
            f"Expected 'Age: ...' format for {case_id}, got: '{age_value}'"
        )
        # Must contain a numeric year or month value
        import re
        assert re.search(r"\d+\s+(year|month)", age_value), (
            f"Precise age format missing numeric year/month for {case_id}: '{age_value}'"
        )

