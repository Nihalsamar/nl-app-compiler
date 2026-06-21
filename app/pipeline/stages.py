"""Individual generation stages. Each builds a prompt, calls the model, and
returns parsed JSON. A small retry guards against transient invalid-JSON
responses without doing a blind full-pipeline retry."""
from __future__ import annotations

from app.llm.base import LLMClient, LLMError

from . import prompts


def _call(client: LLMClient, system: str, user: str, retries: int = 2) -> dict:
    last: Exception | None = None
    for _ in range(retries + 1):
        try:
            return client.complete_json(system, user)
        except LLMError as exc:
            last = exc
    raise last  # type: ignore[misc]


def run_intent(client: LLMClient, user_request: str) -> dict:
    return _call(client, *prompts.intent_prompt(user_request))


def run_design(client: LLMClient, intent: dict) -> dict:
    return _call(client, *prompts.design_prompt(intent))


def run_db(client: LLMClient, intent: dict, design: dict) -> dict:
    return _call(client, *prompts.db_prompt(intent, design))


def run_api(client: LLMClient, intent: dict, design: dict, db: dict) -> dict:
    return _call(client, *prompts.api_prompt(intent, design, db))


def run_ui(client: LLMClient, intent: dict, design: dict, api: dict) -> dict:
    return _call(client, *prompts.ui_prompt(intent, design, api))


def run_auth(client: LLMClient, intent: dict, design: dict, db: dict, api: dict) -> dict:
    return _call(client, *prompts.auth_prompt(intent, design, db, api))
