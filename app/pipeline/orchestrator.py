"""End-to-end orchestration of the generation compiler.

Flow: Intent -> Design -> Schemas -> assemble -> Validate -> Repair -> re-validate.
Collects metrics (latency, retries, failure types, success) for the eval
framework, and surfaces a structured GenerationResult.
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional

from app.llm import get_client
from app.llm.base import LLMClient, LLMError
from app.pipeline import stages
from app.schemas.contracts import AppConfig
from app.validation.repair import repair_config
from app.validation.validator import validate_config


@dataclass
class GenerationMetrics:
    latency_ms: int = 0
    repair_attempts: int = 0
    deterministic_fixes: int = 0
    layers_repaired: List[str] = field(default_factory=list)
    failure_types: List[str] = field(default_factory=list)
    success: bool = False
    needs_clarification: bool = False


@dataclass
class GenerationResult:
    prompt: str
    success: bool
    config: Optional[Dict]
    metrics: GenerationMetrics
    errors: List[str] = field(default_factory=list)
    clarifying_questions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "prompt": self.prompt,
            "success": self.success,
            "config": self.config,
            "metrics": asdict(self.metrics),
            "errors": self.errors,
            "clarifying_questions": self.clarifying_questions,
        }


# Heuristic gate for under-specified prompts -> ask instead of hallucinating.
_VAGUE_MAX_WORDS = 3


def _is_too_vague(prompt: str) -> bool:
    p = prompt.strip()
    return len(p.split()) < _VAGUE_MAX_WORDS


def generate_app(prompt: str, client: Optional[LLMClient] = None) -> GenerationResult:
    client = client or get_client()
    metrics = GenerationMetrics()
    started = time.perf_counter()

    if _is_too_vague(prompt):
        metrics.needs_clarification = True
        metrics.latency_ms = int((time.perf_counter() - started) * 1000)
        return GenerationResult(
            prompt=prompt, success=False, config=None, metrics=metrics,
            clarifying_questions=[
                "What kind of application do you want to build?",
                "What are the main things (entities) it should manage?",
                "Does it need user accounts, roles, or payments?",
            ],
        )

    try:
        intent = stages.run_intent(client, prompt)
        design = stages.run_design(client, intent)
        db = stages.run_db(client, intent, design)
        api = stages.run_api(client, intent, design, db)
        ui = stages.run_ui(client, intent, design, api)
        auth = stages.run_auth(client, intent, design, db, api)
    except LLMError as exc:
        metrics.failure_types.append("llm_error")
        metrics.latency_ms = int((time.perf_counter() - started) * 1000)
        return GenerationResult(
            prompt=prompt, success=False, config=None, metrics=metrics,
            errors=[f"Generation failed: {exc}"],
        )

    config = {
        "app_name": intent.get("app_name", "Generated App"),
        "intent": intent,
        "design": design,
        "db": db,
        "api": api,
        "ui": ui,
        "auth": auth,
    }

    report = validate_config(config)
    if not report.ok:
        metrics.failure_types = sorted({i.code for i in report.errors})
        config, trace = repair_config(client, config, report)
        metrics.repair_attempts = trace.attempts
        metrics.deterministic_fixes = len(trace.deterministic_fixes)
        metrics.layers_repaired = trace.layers_repaired
        report = validate_config(config)

    # Final structural guarantee: must parse into AppConfig.
    final_errors: List[str] = []
    if report.ok:
        try:
            AppConfig.model_validate(config)
        except Exception as exc:  # pragma: no cover - defensive
            report_ok = False
            final_errors.append(f"AppConfig assembly failed: {exc}")
        else:
            report_ok = True
    else:
        report_ok = False
        final_errors = [i.message for i in report.errors]

    metrics.success = report_ok
    metrics.latency_ms = int((time.perf_counter() - started) * 1000)

    # If the model flagged genuine open questions, expose them.
    clarifying = intent.get("open_questions", []) if isinstance(intent, dict) else []

    return GenerationResult(
        prompt=prompt,
        success=report_ok,
        config=config if report_ok else config,
        metrics=metrics,
        errors=final_errors,
        clarifying_questions=clarifying,
    )
