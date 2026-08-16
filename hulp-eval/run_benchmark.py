#!/usr/bin/env python3
"""
run_benchmark.py — Main CLI for running a prompt version against cases.

Usage:
    python run_benchmark.py --prompt prompt_v0 --model anthropic/claude-sonnet-4-6 --set dev
    python run_benchmark.py --prompt prompt_v1 --model anthropic/claude-sonnet-4-6 --set dev
    python run_benchmark.py --prompt prompt_v2 --model anthropic/claude-sonnet-4-6 --set holdout
"""

import argparse
import json
import os
import sys

from adapters.openrouter_adapter import call_model
from graders.aggregate import grade_case, aggregate_results
from run_logger import log_run


def load_cases(case_set: str) -> list[dict]:
    """Load cases filtered by split.json (dev or holdout)."""
    with open("cases/split.json", "r") as f:
        split = json.load(f)

    allowed_ids = set(split.get(case_set, []))
    if not allowed_ids:
        print(f"ERROR: No case IDs found for set '{case_set}' in split.json")
        sys.exit(1)

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
                if case["case_id"] in allowed_ids:
                    cases.append(case)

    loaded_ids = {c["case_id"] for c in cases}
    missing = allowed_ids - loaded_ids
    if missing:
        print(f"WARNING: These case IDs from split.json were not found: {missing}")

    return cases


def format_messages(case: dict) -> str:
    """Format case messages into a user-content string for the model."""
    messages = case.get("messages", [])
    parts = []
    for msg in messages:
        actor = msg.get("actor", "unknown")
        text = msg.get("text", "")
        msg_id = msg.get("id", "?")
        parts.append(f"[{msg_id}] {actor}: {text}")

    # Add metadata if available
    header_parts = []
    if "received_at" in case:
        header_parts.append(f"Received at: {case['received_at']}")
    if "timezone" in case:
        header_parts.append(f"Timezone: {case['timezone']}")

    header = "\n".join(header_parts)
    body = "\n".join(parts)

    if header:
        return f"{header}\n\n{body}"
    return body


def load_schema() -> dict:
    """Load the brief schema."""
    with open("schema/brief_schema.json", "r") as f:
        return json.load(f)


def load_prompt(prompt_name: str) -> str:
    """Load a prompt file by name (e.g. 'prompt_v0' -> prompts/prompt_v0.txt)."""
    path = f"prompts/{prompt_name}.txt"
    if not os.path.exists(path):
        print(f"ERROR: Prompt file not found: {path}")
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


def save_output(prompt_name: str, model_id: str, case_id: str, data: dict) -> None:
    """Cache raw response to outputs/<prompt>/<model_id>/<case_id>.json."""
    # Sanitise model_id for filesystem (replace / with _)
    model_dir = model_id.replace("/", "_")
    out_dir = os.path.join("outputs", prompt_name, model_dir)
    os.makedirs(out_dir, exist_ok=True)

    out_path = os.path.join(out_dir, f"{case_id}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def run_benchmark(prompt_name: str, model_id: str, case_set: str, settings: dict) -> None:
    """Run the benchmark: prompt × model × case set."""
    print(f"\n{'='*70}")
    print(f"  HULP Benchmark Run")
    print(f"  Prompt: {prompt_name}")
    print(f"  Model:  {model_id}")
    print(f"  Set:    {case_set}")
    print(f"  Settings: {settings}")
    print(f"{'='*70}\n")

    system_prompt = load_prompt(prompt_name)
    schema = load_schema()
    cases = load_cases(case_set)

    print(f"Loaded {len(cases)} cases for '{case_set}' set\n")

    case_results = {}
    case_details = {}

    for i, case in enumerate(cases, 1):
        case_id = case["case_id"]
        print(f"[{i}/{len(cases)}] Running {case_id}...", end=" ", flush=True)

        # Build user content
        user_content = format_messages(case)

        # Call model
        try:
            result = call_model(model_id, system_prompt, user_content, settings)
        except Exception as e:
            print(f"ERROR: {e}")
            case_results[case_id] = {
                "schema_valid": False,
                "critical_failure": True,
                "error": str(e),
            }
            continue

        # Log the run
        log_run(case_id, prompt_name, result, settings, user_content)

        # Cache output
        save_output(prompt_name, model_id, case_id, {
            "raw_output": result["raw_output"],
            "prompt_tokens": result["prompt_tokens"],
            "completion_tokens": result["completion_tokens"],
            "cost_usd": result["cost_usd"],
            "latency_ms": result["latency_ms"],
        })

        # Grade
        reference = case.get("reference", {})
        grades = grade_case(result["raw_output"], reference, schema)
        case_results[case_id] = grades

        # Print case result
        status = "PASS" if grades["schema_valid"] and not grades["critical_failure"] else "FAIL"
        if grades["critical_failure"]:
            status = "CRITICAL FAIL"
        print(f"{status} | schema={grades['schema_valid']} | "
              f"constraint_recall={grades.get('constraints', {}).get('recall', 'N/A')} | "
              f"latency={result['latency_ms']}ms")

        case_details[case_id] = {
            "grades": grades,
            "latency_ms": result["latency_ms"],
            "tokens": result["prompt_tokens"] + result["completion_tokens"],
            "cost_usd": result["cost_usd"],
        }

    # Aggregate
    agg = aggregate_results(case_results)

    print(f"\n{'='*70}")
    print(f"  AGGREGATE RESULTS")
    print(f"{'='*70}")
    print(f"  Total cases:              {agg.get('total_cases', 0)}")
    print(f"  Schema validity rate:     {agg.get('schema_validity_rate', 0):.1%}")
    print(f"  Critical failure rate:    {agg.get('critical_failure_rate', 0):.1%}")
    print(f"  Avg constraint recall:    {agg.get('avg_constraint_recall', 0):.1%}")
    print(f"  Avg constraint precision: {agg.get('avg_constraint_precision', 0):.1%}")
    print(f"  Avg risk flag recall:     {agg.get('avg_risk_flag_recall', 0):.1%}")
    print(f"  Avg unsupported claims:   {agg.get('avg_unsupported_claim_rate', 0):.1%}")

    if agg.get("per_case_critical_failures"):
        print(f"\n  Critical failures:")
        for cid, details in agg["per_case_critical_failures"].items():
            print(f"    {cid}: superseded={details['superseded']}, must_not={details['must_not_assert']}")

    # Save summary
    model_dir = model_id.replace("/", "_")
    summary_dir = os.path.join("outputs", prompt_name, model_dir)
    os.makedirs(summary_dir, exist_ok=True)
    summary_path = os.path.join(summary_dir, "summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump({
            "prompt_version": prompt_name,
            "model_id": model_id,
            "case_set": case_set,
            "settings": settings,
            "aggregate": agg,
            "per_case": {
                cid: {
                    "schema_valid": r.get("schema_valid"),
                    "critical_failure": r.get("critical_failure"),
                    "constraint_recall": r.get("constraints", {}).get("recall"),
                    "constraint_precision": r.get("constraints", {}).get("precision"),
                    "risk_flag_recall": r.get("risk_flags", {}).get("recall"),
                    "unsupported_rate": r.get("fact_sourcing", {}).get("unsupported_rate"),
                }
                for cid, r in case_results.items()
            },
        }, f, indent=2, ensure_ascii=False)

    print(f"\n  Summary saved to: {summary_path}")
    print(f"{'='*70}\n")


def main():
    parser = argparse.ArgumentParser(description="HULP Benchmark Runner")
    parser.add_argument("--prompt", required=True, help="Prompt version (e.g. prompt_v0)")
    parser.add_argument("--model", required=True, help="Model slug (e.g. anthropic/claude-sonnet-4-6)")
    parser.add_argument("--set", required=True, choices=["dev", "holdout"], help="Case set to run")
    parser.add_argument("--temperature", type=float, default=0.2, help="Temperature (default: 0.2)")
    parser.add_argument("--max-tokens", type=int, default=2048, help="Max tokens (default: 2048)")

    args = parser.parse_args()

    settings = {
        "temperature": args.temperature,
        "max_tokens": args.max_tokens,
    }

    run_benchmark(args.prompt, args.model, args.set, settings)


if __name__ == "__main__":
    main()
