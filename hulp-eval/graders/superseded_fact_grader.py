"""
Superseded-fact grader — checks that superseded facts do NOT appear in output.
Deterministic: no LLM calls. A hit is a CRITICAL failure.
"""


def grade_superseded(output_text: str, reference: dict) -> dict:
    """
    Check whether any superseded facts from the reference leak into the output.
    
    Args:
        output_text: The full raw model output string
        reference: The case reference dict (must contain 'superseded_facts' if applicable)
    
    Returns:
        dict with leaked_superseded_facts list and critical_failure flag
    """
    superseded = reference.get("superseded_facts", [])
    if not superseded:
        return {
            "leaked_superseded_facts": [],
            "critical_failure": False,
            "total_superseded": 0,
        }

    output_lower = output_text.lower()
    leaked = []
    for term in superseded:
        # Check for the term as a substring (case-insensitive)
        if term.lower() in output_lower:
            leaked.append(term)

    return {
        "leaked_superseded_facts": leaked,
        "critical_failure": len(leaked) > 0,
        "total_superseded": len(superseded),
    }
