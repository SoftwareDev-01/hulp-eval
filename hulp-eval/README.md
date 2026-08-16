# HULP Round 2 — AI Evaluation & Model Improvement Loop

## Overview

Automated evaluation framework for the HULP (Human-in-the-Loop Concierge Platform) briefing assistant. Tests prompt quality, PII handling, and model qualification across multiple LLMs via OpenRouter.

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set your OpenRouter API key
# Edit .env and replace the placeholder:
#   OPENROUTER_API_KEY=sk-or-v1-your-actual-key

# 3. Run tests (no API key needed)
pytest tests/ -v

# 4. Run baseline benchmark (Step 1)
python run_benchmark.py --prompt prompt_v0 --model anthropic/claude-sonnet-4-6 --set dev

# 5. Run prompt iterations (Step 2)
python run_benchmark.py --prompt prompt_v1 --model anthropic/claude-sonnet-4-6 --set dev
python run_benchmark.py --prompt prompt_v2 --model anthropic/claude-sonnet-4-6 --set dev

# 6. Run PII comparison (Step 3)
python run_pii_comparison.py --model anthropic/claude-sonnet-4-6

# 7. Run model qualification on holdout (Step 4)
python run_qualification.py --model-a anthropic/claude-sonnet-4-6 --model-b meta-llama/llama-4-maverick
```

## Project Structure

```
hulp-eval/
├── .env                              # OPENROUTER_API_KEY (never committed)
├── .gitignore
├── README.md                         # This file
├── REPORT.md                         # Evaluation report
├── LOCAL_MODEL_PLAN.md               # Local model deployment plan
├── requirements.txt
├── prompts/
│   ├── prompt_v0.txt                 # Given baseline prompt
│   ├── prompt_v1.txt                 # First iteration
│   └── prompt_v2.txt                 # Second iteration (frozen for Step 4)
├── schema/
│   └── brief_schema.json             # Output schema (locked first)
├── cases/
│   ├── starter_cases.jsonl           # 12 given cases (Y-P01..Y-P12)
│   ├── new_cases.jsonl               # 8 new cases (Y-N01..Y-N08)
│   ├── pii_cases.jsonl               # 4 PII cases (Y-PII01..Y-PII04)
│   └── split.json                    # Dev/holdout split
├── adapters/
│   └── openrouter_adapter.py         # OpenRouter API wrapper
├── context_builder/
│   └── build_model_context.py        # PII field-level classifier
├── graders/
│   ├── schema_grader.py              # JSON schema validation
│   ├── constraint_grader.py          # Fuzzy constraint recall/precision
│   ├── superseded_fact_grader.py     # Superseded fact leak detection
│   ├── must_not_assert_grader.py     # Forbidden assertion detection
│   ├── risk_flag_grader.py           # Risk flag recall
│   ├── model_grader.py              # LLM-assisted fuzzy matching
│   └── aggregate.py                  # Combined grader + aggregation
├── tests/
│   ├── test_pii_boundary.py          # PII boundary tests
│   ├── test_schema.py                # Schema validation tests
│   └── test_graders.py               # Grader unit tests
├── run_benchmark.py                  # Main benchmark CLI
├── run_qualification.py              # Step 4: holdout qualification
├── run_pii_comparison.py             # Step 3: full vs minimised PII
├── run_logger.py                     # Central run logging utility
├── artifacts/
│   └── runs.jsonl                    # Every evaluated call logged here
├── outputs/                          # Cached responses per version/model
│   └── <prompt_version>/<model_id>/<case_id>.json
└── hand_scores/
    └── hand_score_sheet.csv          # Manual scoring of ≥10 outputs
```

## Key Design Decisions

1. **Schema locked first** — All graders depend on `brief_schema.json`. Prompt iterations aim to make models conform to it.
2. **Deterministic graders for critical failures** — Superseded-fact leaks, must-not-assert violations, and PII exclusion are checked with string matching, not LLM calls.
3. **Model grader used sparingly** — Only for fuzzy constraint/topic matching where paraphrasing makes string matching unreliable.
4. **Holdout locked before any tuning** — `split.json` is set once and holdout cases are never run until Step 4.
5. **Single logging point** — `run_logger.py` is the only place that writes to `runs.jsonl`. No duplication.
6. **Explicit model slugs** — Never use `openrouter/auto`. Every run specifies the exact model.

## Grader Architecture

| Grader | Type | What it checks | Failure severity |
|---|---|---|---|
| Schema | Deterministic | Valid JSON + schema conformance | Blocking |
| Superseded Facts | Deterministic | Cancelled/corrected info not in output | **Critical** |
| Must-Not-Assert | Deterministic | Forbidden assertions not in output | **Critical** |
| Constraint Recall/Precision | Deterministic (fuzzy) | Hard constraints matched via token overlap | Soft |
| Risk Flags | Deterministic (keyword) | Required risk flags present | Meaningful |
| Fact Sourcing | Deterministic | Facts have valid source_ids | Soft |
| Model Grader | LLM-assisted | Fuzzy matching for paraphrased items | Soft |

## OpenRouter Setup

1. Create a new OpenRouter account at https://openrouter.ai
2. Copy your API key to `.env`
3. Verify: `python -c "from adapters.openrouter_adapter import call_model; print('OK')"`
