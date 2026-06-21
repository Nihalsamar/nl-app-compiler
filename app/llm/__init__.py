"""LLM provider abstraction with a factory."""
from __future__ import annotations

from app.config import settings

from .base import LLMClient, LLMError
from .mock_client import MockClient

__all__ = ["LLMClient", "LLMError", "get_client"]


def get_client() -> LLMClient:
    settings.validate()
    if settings.provider == "nvidia":
        from .nim_client import NimClient

        return NimClient()
    if settings.provider == "gemini":
        from .gemini_client import GeminiClient

        return GeminiClient()
    return MockClient()
