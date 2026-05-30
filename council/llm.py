"""LLM client using OpenAI-compatible API for zhipu GLM models."""

import os
import re
from typing import Optional
from openai import OpenAI


# Default configuration — zhipu public API
DEFAULT_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
DEFAULT_MODEL = "glm-4-plus"


def get_client() -> OpenAI:
    """Create an OpenAI client configured for zhipu GLM.

    Environment variables (checked in order):
      - OPENAI_API_KEY / ZHIPU_API_KEY — the API key
      - OPENAI_BASE_URL / ZHIPU_BASE_URL — the base URL

    Falls back to sensible defaults for Tower secrets injection.
    """
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("ZHIPU_API_KEY") or ""
    base_url = os.getenv("OPENAI_BASE_URL") or os.getenv("ZHIPU_BASE_URL") or DEFAULT_BASE_URL
    return OpenAI(api_key=api_key, base_url=base_url)


def get_model() -> str:
    """Return the model name to use."""
    return os.getenv("MODEL_NAME") or DEFAULT_MODEL


def call_llm(
    system_prompt: str,
    user_prompt: str,
    model: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> str:
    """Call the LLM with a system and user prompt.

    Args:
        system_prompt: The system role instruction.
        user_prompt: The user message.
        model: Override model name.
        temperature: Sampling temperature (0-1).
        max_tokens: Maximum response tokens.

    Returns:
        The assistant's text response.
    """
    client = get_client()
    model_name = model or get_model()

    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )

    content = response.choices[0].message.content if response.choices else ""
    return content or "Analysis could not be generated."


def extract_confidence(text: str) -> float:
    """Extract a confidence score (0.0-1.0) from LLM output text.

    Looks for patterns like:
      - "confidence: 0.85"
      - "confidence score: 85%"
      - "0.8 / 1.0"

    Returns:
        A float between 0.0 and 1.0, defaulting to 0.7 if not found.
    """
    patterns = [
        r"confidence[:\s]+(\d\.?\d*)",
        r"confidence score[:\s]+(\d\.?\d*)",
        r"(\d\.?\d*)\s*[/\u00f7]\s*1\.0",
        r"(\d+)%\s*confidence",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            val = float(match.group(1))
            if val <= 1.0:
                return val
            if val <= 100:
                return val / 100.0
    return 0.7
