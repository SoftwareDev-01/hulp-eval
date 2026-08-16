"""
Model grader — uses a targeted LLM call for fuzzy constraint/topic matching.
This is the ONLY grader that calls an LLM. Used for cases where paraphrasing
makes string-matching unreliable (hard_constraints, clarification_topics).

NOT used as sole check for critical failures — those stay deterministic.
"""

import json
from adapters.openrouter_adapter import call_model


MATCH_PROMPT = """You are comparing a predicted list against a reference list.

Reference items:
{reference_items}

Predicted items:
{predicted_items}

For each reference item, answer ONLY "matched" or "missing".
A predicted item matches if it captures the same requirement or topic, even with very different wording.

Return valid JSON only, as an array of objects:
[
  {{"reference": "<reference item text>", "verdict": "matched" | "missing"}}
]

Do not include any other text."""


def grade_with_model(
    predicted_items: list[str],
    reference_items: list[str],
    model_id: str = "anthropic/claude-sonnet-4-6",
    item_type: str = "constraints",
) -> dict:
    """
    Use an LLM to do fuzzy matching between predicted and reference lists.
    
    Args:
        predicted_items: The model's output list
        reference_items: The ground-truth reference list
        model_id: Which model to use for grading
        item_type: Label for what's being compared (for logging)
    
    Returns:
        dict with matches, recall, raw_response
    """
    if not reference_items:
        return {
            "item_type": item_type,
            "matches": [],
            "recall": 1.0,
            "raw_response": None,
        }

    if not predicted_items:
        return {
            "item_type": item_type,
            "matches": [{"reference": r, "verdict": "missing"} for r in reference_items],
            "recall": 0.0,
            "raw_response": None,
        }

    prompt = MATCH_PROMPT.format(
        reference_items=json.dumps(reference_items, indent=2),
        predicted_items=json.dumps(predicted_items, indent=2),
    )

    result = call_model(
        model_id=model_id,
        system_prompt="You are a precise evaluation assistant. Return valid JSON only.",
        user_content=prompt,
        settings={"temperature": 0.0, "max_tokens": 1024},
    )

    raw = result["raw_output"]
    # Parse the response
    try:
        # Strip markdown fences if present
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            first_nl = cleaned.index("\n")
            cleaned = cleaned[first_nl + 1:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3].strip()
        matches = json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        # Fallback: treat as all missing
        matches = [{"reference": r, "verdict": "missing"} for r in reference_items]

    matched_count = sum(1 for m in matches if m.get("verdict") == "matched")
    recall = matched_count / len(reference_items) if reference_items else 1.0

    return {
        "item_type": item_type,
        "matches": matches,
        "recall": round(recall, 4),
        "raw_response": raw,
    }
