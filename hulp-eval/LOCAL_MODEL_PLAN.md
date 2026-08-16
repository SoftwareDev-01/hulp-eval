# LOCAL_MODEL_PLAN.md — Local Model Deployment Plan

## 1. Objective

Outline a concrete plan to fine-tune or distil a local model that can replace (or supplement) the hosted API model used in Steps 1–4, while maintaining the quality thresholds established during prompt iteration and qualification.

---

## 2. Data Separation

### Train / Dev / Final-Holdout Split

| Split          | Case IDs                                                                                   | Purpose                           |
|----------------|--------------------------------------------------------------------------------------------|-----------------------------------|
| **Train**      | Y-P01, Y-P03, Y-P05, Y-P06, Y-P10, Y-N01, Y-N02, Y-N03, Y-N04, Y-N05, Y-N06, Y-N07     | SFT / LoRA training data          |
| **Dev**        | Y-PII01, Y-PII02, Y-PII03, Y-PII04                                                       | Hyperparameter tuning, early stop |
| **Final-Holdout** | Y-P02, Y-P04, Y-P07, Y-P08, Y-P09, Y-P11, Y-P12, Y-N08                               | One-shot final evaluation only    |

> **CRITICAL**: The final-holdout set is identical to the Step 4 holdout. These cases must NEVER be used in any training, validation, or prompt-development loop. They exist solely for a single, terminal evaluation pass.

### Leakage Controls
1. **Code-level enforcement**: A `HOLDOUT_IDS` set is defined once in `cases/split.json`. All training scripts import this set and assert no holdout ID appears in their data loader output.
2. **CI gate**: A pre-commit hook (or CI step) greps all generated training JSONL files for holdout IDs and fails the build if any appear.
3. **Prompt isolation**: prompt_v2 was developed against the dev set only. No holdout case influenced any prompt edit.
4. **Indirect leakage**: Hand-scoring of holdout cases is done after all prompt development. The hand-score observations are NOT fed back into prompt edits.

---

## 3. Training Data Construction

### Source: Reviewed Dev-Set Outputs

From the Step 2 prompt iteration, we have high-quality (prompt_v2, Model A) outputs for all 12 dev cases. These become SFT exemplars after manual review:

- **Filter**: Only outputs that scored `pass` on all deterministic graders (schema ✓, no superseded-fact leak, no must-not-assert violation, constraint recall ≥ 95%) are used.
- **Correction**: Where a `partial` output is close to correct, manually fix it to produce a gold output — this adds signal for the failure modes the model still struggles with.
- **Augmentation**: For each training case, generate 2–3 paraphrases of the input messages (different phrasing, same semantics) to increase diversity.

### Targeted Failure-Mode Data

Specific failure modes observed during dev iteration can seed additional training pairs:

| Failure Mode                          | Source Cases       | Training Strategy                                              |
|---------------------------------------|--------------------|-----------------------------------------------------------------|
| Superseded facts leaking              | Y-P02, Y-N02      | Include correction chains with explicit "old fact must vanish"  |
| Must-not-assert violations            | Y-P07              | Include injection examples with correct refusal outputs         |
| Missing-info guess instead of flag    | Y-P08              | Include ambiguous inputs where gold output puts items in `missing_information` |
| Under-triggered risk flags            | Y-P12, Y-N04      | Include cases with subtle risk triggers and correct flag lists  |

### Estimated Dataset Size

- **Core pairs**: 12 dev cases × 3 paraphrases = ~36 input-output pairs
- **Failure-mode enrichment**: ~20 additional pairs targeting specific weaknesses
- **Total**: ~56 pairs for SFT. Small but targeted — LoRA works well at this scale if the base model is already capable.

---

## 4. Model Architecture & Resources

### Base Model
- **Primary candidate**: Qwen2.5-7B-Instruct or Llama-3.1-8B-Instruct
- **Rationale**: 7–8B parameter models are the sweet spot for single-GPU fine-tuning while retaining strong instruction-following. Both support JSON mode and multilingual input (important for Hinglish/Bengali cases).

### Fine-Tuning Approach
- **Method**: QLoRA (4-bit quantised base + LoRA adapters)
- **LoRA config**: rank=16, alpha=32, target_modules=["q_proj", "v_proj", "k_proj", "o_proj"]
- **Training**: 3–5 epochs, learning rate 2e-4 with cosine decay, batch size 4 with gradient accumulation
- **Framework**: Hugging Face TRL + PEFT + bitsandbytes

### Compute Requirements
- **Minimum**: 1× NVIDIA T4 (16 GB VRAM) — sufficient for QLoRA on 7B
- **Preferred**: 1× A100 40GB — faster training, supports 13B models
- **Training time**: ~30 minutes on A100, ~2 hours on T4 for 56 pairs × 5 epochs
- **Inference**: 4-bit quantised model runs on consumer GPU (8 GB VRAM) or CPU with acceptable latency

---

## 5. Evaluation & Acceptance Gates

### Threshold (derived from Step 4 hosted-model qualification)

| Metric                    | Hosted Model Benchmark | Local Model Target |
|---------------------------|------------------------|--------------------|
| Schema validity rate      | 100%                   | ≥ 100%             |
| Critical-failure rate     | 0%                     | 0%                 |
| Constraint recall         | ≥ 95%                  | ≥ 90%              |
| Constraint precision      | ≥ 90%                  | ≥ 85%              |
| Unsupported-claim rate    | ≤ 5%                   | ≤ 10%              |
| Risk-flag recall          | ≥ 90%                  | ≥ 80%              |
| Avg latency               | ~2-4s (API)            | < 10s (local GPU)  |
| Cost per case             | ~$0.01–0.05            | ~$0 (amortised)    |

> **Hard gates** (schema validity = 100%, critical-failure rate = 0%) are non-negotiable. Soft metrics allow a 5–10% regression from hosted model given the cost/latency trade-off.

### Evaluation Protocol
1. Train on train split only.
2. Validate on dev split — tune hyperparameters and early-stop here.
3. Run final-holdout ONCE with the frozen model checkpoint.
4. Compare against hosted model's holdout numbers using the same grader suite.
5. If the local model fails hard gates on holdout → do NOT deploy. Return to step 1 with more data or a larger base model.

---

## 6. Deployment Considerations

- **Serving**: vLLM or llama.cpp for inference serving, exposing an OpenAI-compatible API endpoint.
- **Adapter swap**: The OpenRouter adapter can be trivially re-pointed to `http://localhost:8000/v1` — no application code changes needed.
- **Monitoring**: Log local model runs to the same `runs.jsonl` format. Run the grader suite periodically on a sample of production outputs.
- **Fallback**: If local model degrades, switch back to hosted model via config change (model_id in .env or CLI arg).

---

## 7. Risks & Mitigations

| Risk                                          | Mitigation                                                        |
|-----------------------------------------------|-------------------------------------------------------------------|
| Small training set → overfitting              | LoRA regularisation, early stopping on dev set, data augmentation |
| Bengali/Hinglish underperformance             | Choose base model with multilingual training (Qwen2.5 preferred)  |
| JSON output instability                       | Add JSON-mode constraint in inference, schema validation retry    |
| Holdout leakage during iteration              | Automated CI check, code-level HOLDOUT_IDS enforcement            |
| Regression on edge cases not in training      | Keep hosted model as fallback, monitor via grader suite            |
