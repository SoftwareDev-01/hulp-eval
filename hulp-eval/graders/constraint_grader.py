"""
Constraint grader — recall/precision for hard_constraints using fuzzy token overlap.
Deterministic: no LLM calls.
"""

import re
from typing import List


def _normalize(text: str) -> set:
    """Lowercase, strip punctuation, split into significant tokens."""
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    tokens = text.split()
    # Remove very common stop words
    stop_words = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "shall", "can", "to", "of", "in", "for",
        "on", "with", "at", "by", "from", "as", "into", "through", "during",
        "before", "after", "and", "but", "or", "not", "no", "if", "it", "its",
        "that", "this", "these", "those", "than", "so", "very", "just",
    }
    return {t for t in tokens if t not in stop_words and len(t) > 1}


def _extract_numbers(text: str) -> set:
    """Extract all numeric tokens from text."""
    return set(re.findall(r"\d+", text))


def _token_overlap(a: str, b: str) -> float:
    """
    Return a similarity score between two constraint strings.
    Uses max of Jaccard overlap and containment ratio (intersection / min set size),
    with a boost when key numbers match.
    """
    tokens_a = _normalize(a)
    tokens_b = _normalize(b)
    if not tokens_a or not tokens_b:
        return 0.0

    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    min_size = min(len(tokens_a), len(tokens_b))

    jaccard = len(intersection) / len(union) if union else 0.0
    containment = len(intersection) / min_size if min_size else 0.0

    # Boost if key numbers match (budgets, times, counts)
    nums_a = _extract_numbers(a)
    nums_b = _extract_numbers(b)
    number_match = bool(nums_a and nums_b and nums_a & nums_b)

    base_score = max(jaccard, containment)
    if number_match and len(intersection) >= 1:
        base_score = max(base_score, 0.5)  # Numbers + any shared word = likely match

    return base_score


def _best_match(item: str, candidates: List[str], threshold: float = 0.4) -> str | None:
    """Find the best matching candidate above threshold."""
    best_score = 0.0
    best_candidate = None
    for c in candidates:
        score = _token_overlap(item, c)
        if score > best_score:
            best_score = score
            best_candidate = c
    if best_score >= threshold:
        return best_candidate
    return None


def grade_constraints(predicted: List[str], reference: List[str], threshold: float = 0.4) -> dict:
    """
    Compare predicted hard_constraints against reference hard_constraints
    using fuzzy token overlap.
    
    Returns:
        dict with recall, precision, matched_ref, missed_ref, spurious_pred
    """
    if not reference:
        return {
            "recall": 1.0 if not predicted else 1.0,
            "precision": 1.0 if not predicted else 0.0,
            "matched_ref": [],
            "missed_ref": [],
            "spurious_pred": list(predicted),
        }

    matched_ref = []
    missed_ref = []
    matched_pred = set()

    for ref_item in reference:
        match = _best_match(ref_item, predicted, threshold)
        if match is not None:
            matched_ref.append({"reference": ref_item, "matched_to": match})
            matched_pred.add(match)
        else:
            missed_ref.append(ref_item)

    spurious_pred = [p for p in predicted if p not in matched_pred]

    recall = len(matched_ref) / len(reference) if reference else 1.0
    precision = len(matched_ref) / len(predicted) if predicted else (1.0 if not reference else 0.0)

    return {
        "recall": round(recall, 4),
        "precision": round(precision, 4),
        "matched_ref": matched_ref,
        "missed_ref": missed_ref,
        "spurious_pred": spurious_pred,
    }
