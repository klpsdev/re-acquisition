"""Optional LLM layer. It only writes prose from numbers the engine already computed.

If ANTHROPIC_API_KEY is unset or the call fails, callers fall back to templates.
"""
from __future__ import annotations

import logging

import httpx

from ..config import Settings

log = logging.getLogger(__name__)

SYSTEM = (
    "You write for a small New Jersey residential landlord. Use only the numbers provided in the "
    "input; never invent, recompute or round differently. Plain, direct sentences. No headings, no bullet points."
)


def write(settings: Settings, instruction: str, facts: str, max_tokens: int = 700) -> str | None:
    if not settings.anthropic_api_key:
        return None
    try:
        r = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": settings.anthropic_api_key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": settings.anthropic_model, "max_tokens": max_tokens, "system": SYSTEM,
                  "messages": [{"role": "user", "content": f"{instruction}\n\n<facts>\n{facts}\n</facts>"}]},
            timeout=45,
        )
        r.raise_for_status()
        return "".join(b.get("text", "") for b in r.json().get("content", [])).strip() or None
    except Exception as e:  # noqa: BLE001
        log.warning("LLM call failed, using template: %s", e)
        return None
