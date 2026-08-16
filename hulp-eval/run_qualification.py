#!/usr/bin/env python3
"""
run_qualification.py — Step 4 CLI: runs the locked holdout set on 2 models
with frozen prompt_v2, producing a qualification matrix.

Usage:
    python run_qualification.py --model-a anthropic/claude-sonnet-4-6 --model-b meta-llama/llama-4-maverick
"""

import argparse
import json
import os
import sys

from adapters.openrouter_adapter import call_model
from graders.aggregate import grade_case, aggregate_results
from run_logger import log_run


def load_holdout_cases() -> list[dict]:
    """Load only holdout cases from split.json."""
    with open("cases/split.json", "r") as f:
        split = json.load(f)

    holdout_ids = set(split.get("holdout", []))
    cases = []
    for filename in ["cases/starter_cases.jsonl", "cases/new_cases.jsonl"]:
        if not os.path.exists(filename):
            continue
        with open(filename, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                case = json.loads(line)
                if case["case_id"] in holdout_ids:
                    cases.append(case)
    return cases


def format_messages(case: dict) -> str:
    """Format case messages into a user-content string."""
    messages = case.get("messages", [])
    parts = []
    for msg in messages:
        parts.append(f"[{msg.get('id', '?')}] {msg.get('actor', 'unknown')}: {msg.get('text', '')}")

    header_parts = []
    if "received_at" in case:
        header_parts.append(f"Received at: {case['received_at']}")
    if "timezone" in case:
        header_parts.append(f"Timezone: {case['timezone']}")

    header = "\n".join(header_parts)
    body = "\n".join(parts)
    return f"{header}\n\n{body}" if header else body


def run_model_on_holdout(model_id: str, prompt_text: str, schema: dict, cases: list, settings: dict) -> dict:
    """Run one model on all holdout cases and return results."""
    case_results = {}
    total_cost = 0.0
    total_latency = 0

    for i, case in enumerate(cases, 1):
        case_id = case["case_id"]
        print(f"  [{i}/{len(cases)}] {case_id}...", end=" ", flush=True)

        user_content = format_messages(case)

        try:
            result = call_model(model_id, prompt_text, user_content, settings)
        except Exception as e:
            print(f"ERROR: {e}")
            case_results[case_id] = {
                "schema_valid": False,
                "critical_failure": True,
                "error": str(e),
            }
            continue

        # Log
        log_run(case_id, "prompt_v2", result, settings, user_content)

        # Cache
        model_dir = model_id.replace("/", "_")
        out_dir = os.path.join("outputs", "qualification", model_dir)
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, f"{case_id}.json"), "w") as f:
            json.dump({
                "raw_output": result["raw_output"],
                "prompt_tokens": result["prompt_tokens"],
                "completion_tokens": result["completion_tokens"],
                "cost_usd": result["cost_usd"],
                "latency_ms": result["latency_ms"],
            }, f, indent=2)

        # Grade
        reference = case.get("reference", {})
        grades = grade_case(result["raw_output"], reference, schema)
        case_results[case_id] = grades
        case_results[case_id]["latency_ms"] = result["latency_ms"]
        case_results[case_id]["cost_usd"] = result["cost_usd"]

        total_cost += (result["cost_usd"] or 0)
        total_latency += result["latency_ms"]

        status = "PASS" if grades["schema_valid"] and not grades["critical_failure"] else "FAIL"
        if grades["critical_failure"]:
            status = "CRITICAL FAIL"
        print(f"{status}")

    agg = aggregate_results(case_results)
    agg["total_cost_usd"] = total_cost
    agg["avg_latency_ms"] = total_latency // len(cases) if cases else 0
    agg["cost_per_case"] = total_cost / len(cases) if cases else 0

    return {"aggregate": agg, "per_case": case_results}


def main():
    parser = argparse.ArgumentParser(description="HULP Qualification Runner — Step 4")
    parser.add_argument("--model-a", required=True, help="First model slug")
    parser.add_argument("--model-b", required=True, help="Second model slug")
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--max-tokens", type=int, default=2048)

    args = parser.parse_args()
    settings = {"temperature": args.temperature, "max_tokens": args.max_tokens}

    # Load frozen prompt_v2
    with open("prompts/prompt_v2.txt", "r") as f:
        prompt_text = f.read().strip()

    with open("schema/brief_schema.json", "r") as f:
        schema = json.load(f)

    cases = load_holdout_cases()
    print(f"Loaded {len(cases)} holdout cases\n")

    # Run Model A
    print(f"{'='*60}")
    print(f"  MODEL A: {args.model_a}")
    print(f"{'='*60}")
    results_a = run_model_on_holdout(args.model_a, prompt_text, schema, cases, settings)

    # Run Model B
    print(f"\n{'='*60}")
    print(f"  MODEL B: {args.model_b}")
    print(f"{'='*60}")
    results_b = run_model_on_holdout(args.model_b, prompt_text, schema, cases, settings)

    # Print qualification matrix
    print(f"\n{'='*60}")
    print(f"  QUALIFICATION MATRIX")
    print(f"{'='*60}")

    agg_a = results_a["aggregate"]
    agg_b = results_b["aggregate"]

    header = f"{'Metric':<35} {'Model A':>12} {'Model B':>12}"
    print(header)
    print("-" * len(header))

    metrics = [
        ("Constraint recall", "avg_constraint_recall"),
        ("Constraint precision", "avg_constraint_precision"),
        ("Critical-failure rate", "critical_failure_rate"),
        ("Schema validity rate", "schema_validity_rate"),
        ("Risk flag recall", "avg_risk_flag_recall"),
        ("Unsupported claim rate", "avg_unsupported_claim_rate"),
        ("Avg latency (ms)", "avg_latency_ms"),
        ("Cost per case (USD)", "cost_per_case"),
        ("Total cost (USD)", "total_cost_usd"),
    ]

    for label, key in metrics:
        val_a = agg_a.get(key, "N/A")
        val_b = agg_b.get(key, "N/A")
        if isinstance(val_a, float) and key not in ("avg_latency_ms",):
            val_a_str = f"{val_a:.4f}"
            val_b_str = f"{val_b:.4f}" if isinstance(val_b, float) else str(val_b)
        else:
            val_a_str = str(val_a)
            val_b_str = str(val_b)
        print(f"{label:<35} {val_a_str:>12} {val_b_str:>12}")

    # Save qualification results
    os.makedirs("outputs/qualification", exist_ok=True)
    with open("outputs/qualification/qualification_matrix.json", "w") as f:
        json.dump({
            "model_a": {"model_id": args.model_a, **results_a},
            "model_b": {"model_id": args.model_b, **results_b},
            "settings": settings,
        }, f, indent=2, default=str)

    print(f"\nResults saved to outputs/qualification/qualification_matrix.json")


if __name__ == "__main__":
    main()
