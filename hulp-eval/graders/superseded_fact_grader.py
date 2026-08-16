"""
Superseded-fact grader — checks that superseded facts do NOT appear in output.
Deterministic: no LLM calls. A hit is a CRITICAL failure.

Context-aware: matches inside questions or clarification phrases are skipped
to avoid false positives when the model references a superseded fact only
to confirm it has been replaced (e.g. "Just to confirm, the Noida location
has been changed to Gurgaon?").
"""

import re


# Phrases that signal a question/clarification context (case-insensitive).
_CLARIFICATION_PREFIXES = (
    "do you", "does the", "does your", "did you", "did the",
    "what is", "what are", "what was", "what's",
    "which", "where is", "where are", "when is", "when are",
    "could you", "can you", "would you", "will you",
    "is there", "are there", "is the", "are the",
    "have you", "has the",
    "please confirm", "please clarify", "please specify", "please provide",
    "we need to know", "we would need", "we will need",
    "may i ask", "may we ask",
    "should we", "shall we",
    "just to confirm", "to confirm", "confirming that",
)


def _find_containing_sentences(text: str, term: str) -> list[str]:
    """Find all sentences in text that contain the given term (case-insensitive)."""
    raw_sentences = re.split(r'(?<=[.!?\n])\s*', text)
    raw_sentences = [s.strip() for s in raw_sentences if s.strip()]
    term_lower = term.lower()
    return [s for s in raw_sentences if term_lower in s.lower()]


def _is_question_context(sentence: str) -> bool:
    """
    Determine if a sentence is a question or clarification context.
    """
    s_lower = sentence.lower().strip()

    if sentence.rstrip().endswith("?"):
        return True

    for prefix in _CLARIFICATION_PREFIXES:
        if s_lower.startswith(prefix):
            return True

    return False


def grade_superseded(output_text: str, reference: dict) -> dict:
    """
    Check whether any superseded facts from the reference leak into the output.
    
    Context-aware: if a superseded term only appears inside questions or
    clarification phrases, it is skipped (not counted as a leak).
    
    Args:
        output_text: The full raw model output string
        reference: The case reference dict (must contain 'superseded_facts' if applicable)
    
    Returns:
        dict with leaked_superseded_facts list, skipped_as_questions list,
        and critical_failure flag
    """
    superseded = reference.get("superseded_facts", [])
    if not superseded:
        return {
            "leaked_superseded_facts": [],
            "skipped_as_questions": [],
            "critical_failure": False,
            "total_superseded": 0,
        }

    output_lower = output_text.lower()
    leaked = []
    skipped = []

    for term in superseded:
        if term.lower() not in output_lower:
            continue  # Term not present at all — no issue

        # Term is present — check context
        containing = _find_containing_sentences(output_text, term)

        if not containing:
            # Couldn't split but term is present — be conservative, flag it
            leaked.append(term)
            continue

        # If ALL containing sentences are questions/clarifications, skip
        all_questions = all(_is_question_context(s) for s in containing)
        if all_questions:
            skipped.append({
                "term": term,
                "contexts": containing,
                "reason": "only appears in question/clarification context",
            })
        else:
            leaked.append(term)

    return {
        "leaked_superseded_facts": leaked,
        "skipped_as_questions": skipped,
        "critical_failure": len(leaked) > 0,
        "total_superseded": len(superseded),
    }
