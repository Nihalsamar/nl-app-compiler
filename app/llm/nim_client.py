"""NVIDIA NIM client over the OpenAI-compatible chat completions endpoint.

Uses temperature 0 and requests a JSON object response. Some NIM models reject
`response_format`, so we transparently retry without it and fall back to
prompt-driven JSON extraction.
"""
from __future__ import annotations

import httpx

from app.config import settings

from .base import LLMError, extract_json


class NimClient:
    def __init__(self) -> None:
        self.base_url = settings.nvidia_base_url.rstrip("/")
        self.model = settings.nvidia_model
        self.key = settings.nvidia_api_key
        # Generous read timeout: NIM cold starts / large JSON can be slow.
        self.timeout = httpx.Timeout(180.0, connect=15.0)

    def _post(self, payload: dict) -> httpx.Response:
        return httpx.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.key}",
                "Accept": "application/json",
            },
            json=payload,
            timeout=self.timeout,
        )

    def complete_json(self, system: str, user: str) -> dict:
        base_payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": settings.temperature,
            "max_tokens": settings.max_tokens,
        }
        try:
            resp = self._post({**base_payload, "response_format": {"type": "json_object"}})
            if resp.status_code == 400:
                # model may not support response_format -> retry plain
                resp = self._post(base_payload)
        except httpx.HTTPError as exc:
            raise LLMError(f"NVIDIA NIM request failed: {exc}") from exc

        if resp.status_code != 200:
            raise LLMError(f"NVIDIA NIM HTTP {resp.status_code}: {resp.text[:300]}")

        data = resp.json()
        try:
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise LLMError(f"Unexpected NIM response shape: {data}") from exc
        return extract_json(text)
