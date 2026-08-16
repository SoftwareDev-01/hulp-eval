"""
Aggregate grader — combines all individual grader results into
a case-level summary and cross-case aggregate metrics.
"""

from graders.schema_grader import grade_schema
from graders.constraint_grader import grade_constraints
from graders.superseded_fact_grader import grade_superseded
from graders.must_not_assert_grader import grade_must_not_assert
from graders.risk_flag_grader import grade_risk_flags


def grade_case(output_text: str, reference: dict, schema: dict) -> dict:
    """
    Run all graders on a single case and return a combined result.
    
    Args:
        output_text: Raw model output string
        reference: Case reference dict
        schema: The brief_schema.json loaded as dict
    
    Returns:
        dict with per-grader results and overall case verdict
    """
    results = {}

    # 1. Schema validation
    schema_result = grade_schema(output_text, schema)
    results["schema"] = schema_result

    parsed = schema_result.get("parsed")
    
    # If we have parsed JSON, sanitize it for critical failure graders
    # by removing fields that legitimately contain missing/clarification info
    if parsed:
        import json
        sanitized_parsed = parsed.copy()
        sanitized_parsed["clarification_questions"] = []
        sanitized_parsed["missing_information"] = []
        text_for_critical = json.dumps(sanitized_parsed)
    else:
        text_for_critical = output_text

    # 2. Superseded facts (critical)
    superseded_result = grade_superseded(text_for_critical, reference)
    results["superseded_facts"] = superseded_result

    # 3. Must-not-assert (critical)
    must_not_result = grade_must_not_assert(text_for_critical, reference)
    results["must_not_assert"] = must_not_result

    # If schema is valid, do content-level grading
    if parsed:
        # 4. Constraint recall/precision (deterministic fuzzy)
        pred_constraints = parsed.get("hard_constraints", [])
        ref_constraints = reference.get("hard_constraints", [])
        constraint_result = grade_constraints(pred_constraints, ref_constraints)
        results["constraints"] = constraint_result

        # 5. Risk flags
        pred_risk = parsed.get("risk_flags", [])
        risk_result = grade_risk_flags(pred_risk, reference)
        results["risk_flags"] = risk_result

        # 6. Unsupported claims (facts without valid source_ids)
        facts = parsed.get("facts", [])
        unsupported = [f for f in facts if not f.get("source_ids") or len(f["source_ids"]) == 0]
        unsupported_rate = len(unsupported) / len(facts) if facts else 0.0
        results["fact_sourcing"] = {
            "total_facts": len(facts),
            "unsupported_facts": len(unsupported),
            "unsupported_rate": round(unsupported_rate, 4),
            "unsupported_details": [f["text"][:80] for f in unsupported],
        }
    else:
        results["constraints"] = {"recall": 0.0, "precision": 0.0}
        results["risk_flags"] = {"recall": 0.0, "missed": reference.get("risk_flags", [])}
        results["fact_sourcing"] = {"total_facts": 0, "unsupported_facts": 0, "unsupported_rate": 0.0}

    # Overall case verdict
    critical_failure = (
        superseded_result.get("critical_failure", False)
        or must_not_result.get("critical_failure", False)
    )
    results["critical_failure"] = critical_failure
    results["schema_valid"] = schema_result.get("valid", False)

    return results


def aggregate_results(case_results: dict[str, dict]) -> dict:
    """
    Aggregate per-case grader results into overall metrics.
    
    Args:
        case_results: dict mapping case_id -> grade_case() result
    
    Returns:
        dict with aggregate metrics
    """
    total = len(case_results)
    if total == 0:
        return {}

    schema_valid_count = sum(1 for r in case_results.values() if r.get("schema_valid"))
    critical_failure_count = sum(1 for r in case_results.values() if r.get("critical_failure"))

    constraint_recalls = []
    constraint_precisions = []
    risk_recalls = []
    unsupported_rates = []

    for r in case_results.values():
        c = r.get("constraints", {})
        if "recall" in c:
            constraint_recalls.append(c["recall"])
        if "precision" in c:
            constraint_precisions.append(c["precision"])

        rf = r.get("risk_flags", {})
        if "recall" in rf:
            risk_recalls.append(rf["recall"])

        fs = r.get("fact_sourcing", {})
        if "unsupported_rate" in fs:
            unsupported_rates.append(fs["unsupported_rate"])

    def avg(lst):
        return round(sum(lst) / len(lst), 4) if lst else 0.0

    return {
        "total_cases": total,
        "schema_validity_rate": round(schema_valid_count / total, 4),
        "critical_failure_rate": round(critical_failure_count / total, 4),
        "critical_failure_count": critical_failure_count,
        "avg_constraint_recall": avg(constraint_recalls),
        "avg_constraint_precision": avg(constraint_precisions),
        "avg_risk_flag_recall": avg(risk_recalls),
        "avg_unsupported_claim_rate": avg(unsupported_rates),
        "per_case_critical_failures": {
            cid: {
                "superseded": r.get("superseded_facts", {}).get("leaked_superseded_facts", []),
                "must_not_assert": r.get("must_not_assert", {}).get("violated_assertions", []),
            }
            for cid, r in case_results.items()
            if r.get("critical_failure")
        },
    }
