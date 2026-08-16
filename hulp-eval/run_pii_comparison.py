#!/usr/bin/env python3
"""
run_pii_comparison.py — Step 3: PII Context Builder evaluation.

Runs all 4 PII cases twice:
  1. Full context (entire available_context dumped into prompt)
  2. Minimised context (through build_model_context)

Produces a comparison table: accuracy, critical failures, tokens, cost.

Usage:
    python run_pii_comparison.py --model anthropic/claude-sonnet-4-6
"""

import argparse
import json
import os
import sys

from adapters.openrouter_adapter import call_model
from context_builder.build_model_context import build_model_context
from graders.aggregate import grade_case
from run_logger import log_run


def load_pii_cases() -> list[dict]:
    """Load all PII cases."""
    cases = []
    with open("cases/pii_cases.jsonl", "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            cases.append(json.loads(line))
    return cases


def format_messages_from_task(task: dict) -> str:
    """Format messages from a PII case's task field."""
    messages = task.get("messages", [])
    parts = []
    for msg in messages:
        parts.append(f"[{msg.get('id', '?')}] {msg.get('actor', 'unknown')}: {msg.get('text', '')}")

    header_parts = []
    if "received_at" in task:
        header_parts.append(f"Received at: {task['received_at']}")

    header = "\n".join(header_parts)
    body = "\n".join(parts)
    return f"{header}\n\n{body}" if header else body


def run_pii_comparison(model_id: str, settings: dict) -> None:
    """Run full vs minimised comparison on all PII cases."""

    with open("prompts/prompt_v2.txt", "r") as f:
        prompt_text = f.read().strip()
    with open("schema/brief_schema.json", "r") as f:
        schema = json.load(f)

    cases = load_pii_cases()
    print(f"Loaded {len(cases)} PII cases\n")

    results = []

    for case in cases:
        case_id = case["case_id"]
        task = case.get("task", {})
        available_context = case.get("available_context", {})
        reference = case.get("reference", {})

        # Build a reference dict compatible with grade_case
        # PII cases use task_invariants instead of hard_constraints
        grade_ref = {
            "hard_constraints": reference.get("task_invariants", []),
            "risk_flags": reference.get("risk_flags", []),
            "must_not_assert": reference.get("must_not_assert", []),
            "superseded_facts": reference.get("superseded_facts", []),
        }

        messages_text = format_messages_from_task(task)

        # ─── Run 1: FULL context ──────────────────────────────────────
        print(f"[{case_id}] Running FULL context...", end=" ", flush=True)

        full_context_str = json.dumps(available_context, indent=2, ensure_ascii=False)
        full_user_content = f"{messages_text}\n\nAvailable context:\n{full_context_str}"

        try:
            full_result = call_model(model_id, prompt_text, full_user_content, settings)
            log_run(case_id, "prompt_v2_full_context", full_result, settings, full_user_content)
            full_grades = grade_case(full_result["raw_output"], grade_ref, schema)
            print(f"OK ({full_result['latency_ms']}ms, "
                  f"{full_result['prompt_tokens']+full_result['completion_tokens']} tokens)")
        except Exception as e:
            print(f"ERROR: {e}")
            full_result = {"prompt_tokens": 0, "completion_tokens": 0, "cost_usd": 0, "latency_ms": 0}
            full_grades = {"schema_valid": False, "critical_failure": True}

        # ─── Run 2: MINIMISED context ─────────────────────────────────
        print(f"[{case_id}] Running MINIMISED context...", end=" ", flush=True)

        minimised = build_model_context(available_context)
        min_context_str = json.dumps(minimised["model_payload"], indent=2, ensure_ascii=False)
        min_user_content = f"{messages_text}\n\nAvailable context:\n{min_context_str}"

        # Verify no excluded PII in the minimised content
        pii_leak = False
        excluded_values = ["4819", "VL-887102", "4321-7788-9012", "HI-2944021",
                           "Z7719920", "tok_live_72PX", "KSR-44",
                           "+91-98111-22334", "+91-98990-11223", "+91-99770-33118"]
        for val in excluded_values:
            if val in min_user_content:
                print(f"\n  ⚠ PII LEAK: '{val}' found in minimised context!")
                pii_leak = True

        try:
            min_result = call_model(model_id, prompt_text, min_user_content, settings)
            log_run(case_id, "prompt_v2_min_context", min_result, settings, min_user_content)
            min_grades = grade_case(min_result["raw_output"], grade_ref, schema)
            print(f"OK ({min_result['latency_ms']}ms, "
                  f"{min_result['prompt_tokens']+min_result['completion_tokens']} tokens)")
        except Exception as e:
            print(f"ERROR: {e}")
            min_result = {"prompt_tokens": 0, "completion_tokens": 0, "cost_usd": 0, "latency_ms": 0}
            min_grades = {"schema_valid": False, "critical_failure": True}

        results.append({
            "case_id": case_id,
            "full": {
                "schema_valid": full_grades.get("schema_valid", False),
                "critical_failure": full_grades.get("critical_failure", False),
                "constraint_recall": full_grades.get("constraints", {}).get("recall", 0),
                "tokens": full_result.get("prompt_tokens", 0) + full_result.get("completion_tokens", 0),
                "cost_usd": full_result.get("cost_usd", 0),
                "latency_ms": full_result.get("latency_ms", 0),
            },
            "minimised": {
                "schema_valid": min_grades.get("schema_valid", False),
                "critical_failure": min_grades.get("critical_failure", False),
                "constraint_recall": min_grades.get("constraints", {}).get("recall", 0),
                "tokens": min_result.get("prompt_tokens", 0) + min_result.get("completion_tokens", 0),
                "cost_usd": min_result.get("cost_usd", 0),
                "latency_ms": min_result.get("latency_ms", 0),
                "pii_leak": pii_leak,
            },
            "field_manifest": minimised["field_manifest"],
        })

    # ─── Print comparison table ───────────────────────────────────────
    print(f"\n{'='*90}")
    print(f"  PII CONTEXT COMPARISON: FULL vs MINIMISED")
    print(f"{'='*90}")

    header = (f"{'Case':<10} | {'Accuracy(F)':>11} | {'Accuracy(M)':>11} | "
              f"{'CritFail(F)':>11} | {'CritFail(M)':>11} | "
              f"{'Tokens(F)':>9} | {'Tokens(M)':>9} | "
              f"{'Cost(F)':>8} | {'Cost(M)':>8}")
    print(header)
    print("-" * len(header))

    for r in results:
        f = r["full"]
        m = r["minimised"]
        print(f"{r['case_id']:<10} | "
              f"{f['constraint_recall']:>11.2f} | {m['constraint_recall']:>11.2f} | "
              f"{str(f['critical_failure']):>11} | {str(m['critical_failure']):>11} | "
              f"{f['tokens']:>9} | {m['tokens']:>9} | "
              f"{(f['cost_usd'] or 0):>8.5f} | {(m['cost_usd'] or 0):>8.5f}")

    # ─── Save results ────────────────────────────────────────────────
    os.makedirs("outputs/pii_comparison", exist_ok=True)
    with open("outputs/pii_comparison/comparison.json", "w") as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\nResults saved to outputs/pii_comparison/comparison.json")

    # ─── Print field manifest summary ─────────────────────────────────
    print(f"\n{'='*90}")
    print(f"  FIELD MANIFEST SUMMARY")
    print(f"{'='*90}")

    all_fields = {}
    for r in results:
        for entry in r["field_manifest"]:
            field = entry["field"]
            if field not in all_fields:
                all_fields[field] = entry

    print(f"{'Field':<30} | {'Action':<12} | {'Purpose'}")
    print("-" * 80)
    for field, entry in sorted(all_fields.items()):
        print(f"{field:<30} | {entry['action']:<12} | {entry['purpose']}")


def main():
    parser = argparse.ArgumentParser(description="HULP PII Comparison Runner")
    parser.add_argument("--model", required=True, help="Model slug")
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--max-tokens", type=int, default=2048)

    args = parser.parse_args()
    settings = {"temperature": args.temperature, "max_tokens": args.max_tokens}

    run_pii_comparison(args.model, settings)


if __name__ == "__main__":
    main()
