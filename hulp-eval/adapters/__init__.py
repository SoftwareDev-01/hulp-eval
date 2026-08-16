"""
OpenRouter adapter — thin wrapper around the OpenAI-compatible API.
Always use explicit model slugs; never use openrouter/auto.
"""

import os
import time
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.environ["OPENROUTER_API_KEY"],
)


def call_model(
    model_id: str,
    system_prompt: str,
    user_content: str,
    settings: dict | None = None,
) -> dict:
    """
    Call a model via OpenRouter and return structured metadata.
    
    Args:
        model_id: Explicit model slug, e.g. "anthropic/claude-sonnet-4-6"
        system_prompt: System-level instruction (the prompt version text)
        user_content: The user-facing content (case messages formatted as text)
        settings: Optional dict with temperature, max_tokens overrides
    
    Returns:
        dict with raw_output, token counts, cost, latency, model info
    """
    if settings is None:
        settings = {}

    start = time.time()
    response = client.chat.completions.create(
        model=model_id,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        temperature=settings.get("temperature", 0.2),
        max_tokens=settings.get("max_tokens", 2048),
    )
    latency_ms = int((time.time() - start) * 1000)

    usage = response.usage
    # OpenRouter may or may not return cost — handle gracefully
    cost = None
    if usage and hasattr(usage, "cost"):
        cost = usage.cost

    return {
        "raw_output": response.choices[0].message.content,
        "prompt_tokens": usage.prompt_tokens if usage else 0,
        "completion_tokens": usage.completion_tokens if usage else 0,
        "cost_usd": cost,
        "latency_ms": latency_ms,
        "model_id": model_id,
        "provider": model_id.split("/")[0],
    }
