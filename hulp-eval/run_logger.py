"""
Run logger — appends every evaluated call to artifacts/runs.jsonl.
Single source of truth for logging — all scripts call this, no duplication.
"""

import json
import os
from datetime import datetime, timezone


RUNS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "artifacts", "runs.jsonl")


def log_run(
    case_id: str,
    prompt_version: str,
    result: dict,
    model_settings: dict,
    model_input: str,
) -> None:
    """
    Append a single run entry to artifacts/runs.jsonl.
    
    Args:
        case_id: The case identifier
        prompt_version: e.g. "prompt_v0", "prompt_v1"
        result: Return value from call_model()
        model_settings: The settings dict used for the call
        model_input: The user_content string sent to the model
    """
    entry = {
        "case_id": case_id,
        "prompt_version": prompt_version,
        "model_id": result["model_id"],
        "provider": result["provider"],
        "model_settings": model_settings,
        "model_input": model_input,
        "raw_output": result["raw_output"],
        "prompt_tokens": result["prompt_tokens"],
        "completion_tokens": result["completion_tokens"],
        "cost_usd": result["cost_usd"],
        "latency_ms": result["latency_ms"],
        "timestamp": datetime.now(timezone.utc).astimezone().isoformat(),
    }

    os.makedirs(os.path.dirname(RUNS_FILE), exist_ok=True)
    with open(RUNS_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
