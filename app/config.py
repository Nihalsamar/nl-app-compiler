"""Runtime configuration, loaded from environment / .env."""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    provider: str = os.getenv("LLM_PROVIDER", "mock").lower()

    # NVIDIA NIM (OpenAI-compatible)
    nvidia_api_key: str = os.getenv("NVIDIA_API_KEY", "")
    nvidia_base_url: str = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
    nvidia_model: str = os.getenv("NVIDIA_MODEL", "meta/llama-3.3-70b-instruct")

    # Google Gemini
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

    temperature: float = float(os.getenv("LLM_TEMPERATURE", "0"))
    max_tokens: int = int(os.getenv("LLM_MAX_TOKENS", "4096"))

    @property
    def model(self) -> str:
        """The active model name for the selected provider (for display)."""
        if self.provider == "nvidia":
            return self.nvidia_model
        if self.provider == "gemini":
            return self.gemini_model
        return "mock"

    def validate(self) -> None:
        if self.provider == "nvidia" and not self.nvidia_api_key:
            raise RuntimeError(
                "LLM_PROVIDER=nvidia but NVIDIA_API_KEY is empty. "
                "Add your key to .env or set LLM_PROVIDER=mock."
            )
        if self.provider == "gemini" and not self.gemini_api_key:
            raise RuntimeError(
                "LLM_PROVIDER=gemini but GEMINI_API_KEY is empty. "
                "Add your key to .env or set LLM_PROVIDER=mock."
            )


settings = Settings()
