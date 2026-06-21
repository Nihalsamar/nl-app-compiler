"""Tests run against the deterministic mock provider (no network, no key)."""
from __future__ import annotations

from app.llm.mock_client import MockClient
from app.pipeline.orchestrator import generate_app
from app.runtime.engine import RuntimeApp
from app.schemas.contracts import AppConfig
from app.validation.repair import repair_config
from app.validation.validator import ValidationReport, validate_config

CLIENT = MockClient()


def test_crm_generates_valid_executable_config():
    res = generate_app(
        "Build a CRM with login, contacts, dashboard, role-based access, "
        "and a premium plan with payments. Admins can see analytics.",
        client=CLIENT,
    )
    assert res.success
    AppConfig.model_validate(res.config)  # parses into the strict contract
    assert validate_config(res.config).ok
    assert RuntimeApp(res.config).smoke_test()["executable"]


def test_simple_task_app():
    res = generate_app("Build a task manager where users create tasks.", client=CLIENT)
    assert res.success
    entities = [e["name"] for e in res.config["design"]["entities"]]
    assert "task" in entities


def test_vague_prompt_asks_for_clarification():
    res = generate_app("app", client=CLIENT)
    assert not res.success
    assert res.metrics.needs_clarification
    assert res.clarifying_questions


def test_validator_flags_dangling_endpoint():
    res = generate_app("Build a task manager where users create tasks.", client=CLIENT)
    cfg = res.config
    # Corrupt a UI binding -> validator must catch it.
    cfg["ui"]["pages"][0]["components"][0]["bound_endpoint"] = "GET /does-not-exist"
    report = validate_config(cfg)
    assert not report.ok
    assert any(i.code == "dangling_endpoint" for i in report.errors)


def test_validator_flags_entity_without_table():
    res = generate_app("Build a task manager where users create tasks.", client=CLIENT)
    cfg = res.config
    cfg["db"]["tables"] = [t for t in cfg["db"]["tables"] if t["name"] != "tasks"]
    report = validate_config(cfg)
    assert not report.ok
    assert any(i.code == "entity_without_table" for i in report.errors)


def test_repair_is_noop_on_valid_mock_config():
    res = generate_app("Build a blog with posts and comments.", client=CLIENT)
    report = validate_config(res.config)
    fixed, trace = repair_config(CLIENT, res.config, report)
    assert validate_config(fixed).ok
    assert trace.attempts == 0
