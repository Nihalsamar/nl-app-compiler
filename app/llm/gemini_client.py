"""Gemini client over the REST API (no SDK dependency, just httpx).

Uses `responseMimeType: application/json` and temperature 0 to push the model
toward valid, deterministic JSON. Network/quota errors raise LLMError so the
orchestrator can surface them cleanly.
"""
from __future__ import annotations

import httpx

from app.config import settings

from .base import LLMError, extract_json

_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiClient:
    def __init__(self) -> None:
        self.model = settings.model
        self.key = settings.gemini_api_key
        self.timeout = 60.0

    def complete_json(self, system: str, user: str) -> dict:
        url = f"{_BASE}/{self.model}:generateContent"
        payload = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {
                "temperature": settings.temperature,
                "maxOutputTokens": settings.max_tokens,
                "responseMimeType": "application/json",
            },
        }
        try:
            resp = httpx.post(
                url,
                params={"key": self.key},
                json=payload,
                timeout=self.timeout,
            )
        except httpx.HTTPError as exc:
            raise LLMError(f"Gemini request failed: {exc}") from exc

        if resp.status_code != 200:
            raise LLMError(
                f"Gemini HTTP {resp.status_code}: {resp.text[:300]}"
            )

        data = resp.json()
        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError) as exc:
            raise LLMError(f"Unexpected Gemini response shape: {data}") from exc
        return extract_json(text)
