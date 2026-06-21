"""LLM client protocol and JSON extraction helper.

Stages talk to the model only through `complete_json`, which must return a
parsed dict. Concrete clients coax valid JSON out of the provider; the pipeline
never sees raw text.
"""
from __future__ import annotations

import json
from typing import Protocol


class LLMError(RuntimeError):
    pass


class LLMClient(Protocol):
    def complete_json(self, system: str, user: str) -> dict: ...


def extract_json(text: str) -> dict:
    """Best-effort extraction of a JSON object from model text.

    Handles fenced code blocks and surrounding prose. Raises LLMError when no
    JSON object can be parsed -- the repair engine treats that as an
    'invalid JSON' failure and regenerates the offending stage.
    """
    text = (text or "").strip()
    if text.startswith("```"):
        parts = text.split("```")
        if len(parts) >= 2:
            text = parts[1]
            if text.lstrip().lower().startswith("json"):
                text = text.lstrip()[4:]
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise LLMError(f"No JSON object found in model output: {text[:200]!r}")
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise LLMError(f"Invalid JSON from model: {exc}") from exc
