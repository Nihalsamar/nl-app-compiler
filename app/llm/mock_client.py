"""Deterministic, offline LLM stand-in.

It never calls a network. Given the same prompt it always returns the same
structured output, which makes it ideal for tests, CI, and demoing the
pipeline/validation/runtime without spending tokens. It is intentionally
"dumb" (keyword heuristics) -- its job is to exercise the engineering around
the model, not to be smart.

The stage is signalled via a `stage=<name>` marker the prompt layer embeds in
the system prompt. Prior-stage context is passed as a JSON object in the user
prompt and recovered with `extract_json`.
"""
from __future__ import annotations

import json
import re
from typing import List

from .base import extract_json

_ENTITY_KEYWORDS = [
    "contact", "customer", "user", "task", "todo", "product", "order",
    "post", "comment", "project", "invoice", "ticket", "lead", "deal",
    "appointment", "booking", "course", "lesson", "note", "expense",
    "transaction", "review", "article", "event", "message",
]


def _detect_stage(system: str) -> str:
    m = re.search(r"stage=(\w+)", system)
    return m.group(1) if m else "intent"


def _singular(word: str) -> str:
    if word.endswith("ies"):
        return word[:-3] + "y"
    if word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _detect_entities(text: str) -> List[str]:
    t = text.lower()
    found: List[str] = []
    for kw in _ENTITY_KEYWORDS:
        if kw in t and kw not in found:
            found.append(kw)
    # de-dupe overlaps like user/customer, todo/task
    if "todo" in found and "task" in found:
        found.remove("todo")
    if not found:
        found = ["item"]
    return found[:6]


def _build_intent(prompt: str) -> dict:
    t = prompt.lower()
    entities = _detect_entities(prompt)
    has_auth = any(w in t for w in ["login", "auth", "role", "sign in", "account"])
    has_payments = any(
        w in t for w in ["payment", "premium", "plan", "subscription", "billing", "pay"]
    )
    roles: List[str] = []
    if "admin" in t:
        roles.append("admin")
    if has_auth or "user" in t:
        roles.append("user")
    if not roles:
        roles = ["user"]
    name_match = re.search(r"build (?:a|an)\s+([a-z0-9 ]{2,30}?)(?: with| that| for|\.|$)", t)
    app_name = (name_match.group(1).strip().title() if name_match else "Generated App")
    features = [f"Manage {e}s" for e in entities]
    if has_auth:
        features.append("Authentication and role-based access")
    if has_payments:
        features.append("Premium plan with payments")
    return {
        "app_name": app_name,
        "summary": prompt.strip()[:200] or "A generated application.",
        "features": features,
        "entities": entities,
        "roles": roles,
        "has_auth": has_auth,
        "has_payments": has_payments,
        "assumptions": [
            "Email/password auth assumed where login is mentioned."
        ] if has_auth else [],
        "open_questions": [],
    }


def _build_design(intent: dict) -> dict:
    roles = intent.get("roles", ["user"])
    entities = intent.get("entities", ["item"])
    owner = "admin" if "admin" in roles else roles[0]
    return {
        "entities": [
            {"name": e, "description": f"Represents a {e}.", "owned_by_role": owner}
            for e in entities
        ],
        "roles": roles,
        "flows": [
            {"name": f"{e} lifecycle", "steps": ["create", "read", "update", "delete"]}
            for e in entities
        ],
        "premium_features": (
            [f"Advanced {entities[0]} analytics"] if intent.get("has_payments") else []
        ),
    }


def _build_schemas(intent: dict, design: dict) -> dict:
    entities = [e["name"] for e in design.get("entities", [])] or ["item"]
    roles = design.get("roles", ["user"])
    has_auth = intent.get("has_auth", False)

    tables = []
    for e in entities:
        cols = [
            {"name": "id", "type": "integer", "primary_key": True, "required": True},
            {"name": "name", "type": "string", "required": True},
            {"name": "description", "type": "text", "required": False},
            {"name": "created_at", "type": "datetime", "required": True},
        ]
        if has_auth:
            cols.append({
                "name": "owner_id", "type": "foreign_key",
                "required": True, "references": "users.id",
            })
        tables.append({"name": _singular(e) + "s", "columns": cols})
    if has_auth:
        tables.insert(0, {"name": "users", "columns": [
            {"name": "id", "type": "integer", "primary_key": True, "required": True},
            {"name": "email", "type": "string", "required": True},
            {"name": "role", "type": "string", "required": True},
        ]})

    endpoints = []
    for e in entities:
        base = "/" + _singular(e) + "s"
        common_fields = [
            {"name": "name", "type": "string", "required": True},
            {"name": "description", "type": "text", "required": False},
        ]
        id_field = [{"name": "id", "type": "integer", "required": True}]
        endpoints += [
            {"path": base, "method": "GET", "entity": e,
             "description": f"List {e}s", "request_fields": [],
             "response_fields": id_field + common_fields, "allowed_roles": roles},
            {"path": base, "method": "POST", "entity": e,
             "description": f"Create {e}", "request_fields": common_fields,
             "response_fields": id_field + common_fields, "allowed_roles": roles},
            {"path": base + "/{id}", "method": "PUT", "entity": e,
             "description": f"Update {e}", "request_fields": common_fields,
             "response_fields": id_field + common_fields, "allowed_roles": roles},
            {"path": base + "/{id}", "method": "DELETE", "entity": e,
             "description": f"Delete {e}", "request_fields": [],
             "response_fields": [], "allowed_roles": roles},
        ]

    pages = []
    for e in entities:
        base = "/" + _singular(e) + "s"
        pages.append({
            "name": f"{e.title()}s",
            "path": base,
            "components": [
                {"type": "table", "entity": e, "fields": ["id", "name", "description"],
                 "bound_endpoint": f"GET {base}"},
                {"type": "form", "entity": e, "fields": ["name", "description"],
                 "bound_endpoint": f"POST {base}"},
            ],
            "visible_to_roles": roles,
        })
    pages.append({
        "name": "Dashboard", "path": "/dashboard",
        "components": [{"type": "dashboard", "entity": None, "fields": [], "bound_endpoint": None}],
        "visible_to_roles": roles,
    })

    permissions = []
    for r in roles:
        for e in entities:
            actions = ["GET", "POST", "PUT", "DELETE"] if r == "admin" or len(roles) == 1 \
                else ["GET", "POST"]
            permissions.append({"role": r, "entity": e, "actions": actions})

    auth = {
        "enabled": has_auth,
        "roles": roles if has_auth else [],
        "permissions": permissions if has_auth else [],
        "premium_gated_entities": (
            [entities[0]] if intent.get("has_payments") else []
        ),
    }

    return {
        "db": {"tables": tables},
        "api": {"endpoints": endpoints},
        "ui": {"pages": pages},
        "auth": auth,
    }


class MockClient:
    def complete_json(self, system: str, user: str) -> dict:
        stage = _detect_stage(system)
        if stage == "intent":
            return _build_intent(user)
        ctx = extract_json(user)
        if stage == "design":
            return _build_design(ctx.get("intent", ctx))
        if stage in ("db", "api", "ui", "auth"):
            schemas = _build_schemas(ctx.get("intent", {}), ctx.get("design", {}))
            return schemas[stage]
        if stage == "schemas":
            return _build_schemas(ctx.get("intent", {}), ctx.get("design", {}))
        if stage.startswith("repair:"):
            # The mock is already internally consistent, so "repair" just
            # echoes the current (valid) layer back unchanged.
            layer = stage.split(":", 1)[1]
            return ctx.get("current_config", {}).get(layer, {})
        if stage == "refine":
            return ctx
        raise ValueError(f"Unknown stage: {stage}")
