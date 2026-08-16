"""
Schema grader — validates model output against brief_schema.json.
Deterministic: no LLM calls.
"""

import json
import jsonschema


def grade_schema(output_text: str, schema: dict) -> dict:
    """
    Validate that output_text is valid JSON conforming to the given schema.
    
    Returns:
        dict with 'valid' (bool), optionally 'parsed' (dict) or 'error' (str)
    """
    # Strip markdown fences if model wrapped output
    cleaned = output_text.strip()
    if cleaned.startswith("```"):
        # Remove opening fence (```json or ```)
        first_newline = cleaned.index("\n")
        cleaned = cleaned[first_newline + 1:]
        # Remove closing fence
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as e:
        return {"valid": False, "error": f"not valid JSON: {e}", "parsed": None}

    try:
        jsonschema.validate(parsed, schema)
        return {"valid": True, "parsed": parsed}
    except jsonschema.ValidationError as e:
        return {"valid": False, "error": str(e.message), "parsed": parsed}
