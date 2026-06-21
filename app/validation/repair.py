"""Repair engine: deterministic first, LLM second.

Strategy (this is the core "control" piece of the system):

1. Deterministic repair -- mechanical inconsistencies are fixed in code, not by
   re-prompting. Aligning an API field type to its DB column, pruning a UI field
   that no API exposes, or registering a role used but undeclared are all
   unambiguous fixes. Doing them deterministically removes model variance and is
   far more reliable than asking an LLM to "try again".

2. LLM repair -- only the issues that need genuine regeneration (e.g. an entity
   with no table at all) are sent back to the model, one affected layer at a
   time, with the exact problems to fix. Never a blind full retry.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from app.llm.base import LLMClient, LLMError
from app.naming import table_name
from app.pipeline import prompts
from app.validation.validator import ValidationReport, validate_config


@dataclass
class RepairTrace:
    deterministic_fixes: List[str] = field(default_factory=list)
    llm_attempts: int = 0
    layers_repaired: List[str] = field(default_factory=list)
    remaining_errors: List[str] = field(default_factory=list)

    # kept for backwards-compatible metrics
    @property
    def attempts(self) -> int:
        return self.llm_attempts


# --------------------------------------------------------------------------- #
# Deterministic repair
# --------------------------------------------------------------------------- #
def _endpoint_keys(api: Dict) -> set:
    return {f"{e.get('method')} {e.get('path')}" for e in api.get("endpoints", [])}


def _api_fields_by_entity(api: Dict) -> Dict[str, set]:
    out: Dict[str, set] = {}
    for ep in api.get("endpoints", []):
        bucket = out.setdefault(ep.get("entity", ""), set())
        for f in ep.get("request_fields", []) + ep.get("response_fields", []):
            bucket.add(f["name"])
    return out


def deterministic_repair(config: Dict) -> tuple[Dict, List[str]]:
    fixes: List[str] = []
    db = config.get("db", {}) or {}
    api = config.get("api", {}) or {}
    ui = config.get("ui", {}) or {}
    auth = config.get("auth", {}) or {}

    columns = {
        t["name"]: {c["name"]: c for c in t.get("columns", [])}
        for t in db.get("tables", [])
    }

    # 1. API field types -> match DB column types.
    for ep in api.get("endpoints", []):
        cols = columns.get(table_name(ep.get("entity", "")), {})
        for f in ep.get("request_fields", []) + ep.get("response_fields", []):
            col = cols.get(f["name"])
            if col and f["name"] != "id" and col["type"] != f.get("type"):
                fixes.append(
                    f"api: aligned '{ep.get('entity')}.{f['name']}' type "
                    f"{f.get('type')} -> {col['type']}"
                )
                f["type"] = col["type"]

    # 2. UI: prune fields not exposed by the API; fix/drop dangling bindings.
    ep_keys = _endpoint_keys(api)
    fields_by_entity = _api_fields_by_entity(api)
    pref = {"table": "GET", "detail": "GET", "form": "POST"}
    by_entity_method = {}
    for ep in api.get("endpoints", []):
        by_entity_method.setdefault((ep.get("entity"), ep.get("method")), ep)
    for page in ui.get("pages", []):
        for comp in page.get("components", []):
            ent = comp.get("entity")
            if ent and ent in fields_by_entity and comp.get("fields"):
                kept = [f for f in comp["fields"] if f in fields_by_entity[ent]]
                if len(kept) != len(comp["fields"]):
                    fixes.append(f"ui: pruned unknown fields on '{page.get('name')}'")
                    comp["fields"] = kept
            be = comp.get("bound_endpoint")
            if be and be not in ep_keys:
                method = pref.get(comp.get("type"), "GET")
                cand = by_entity_method.get((ent, method))
                if cand:
                    comp["bound_endpoint"] = f"{cand['method']} {cand['path']}"
                    fixes.append(f"ui: rebound dangling endpoint to {comp['bound_endpoint']}")
                else:
                    comp["bound_endpoint"] = None
                    fixes.append("ui: dropped dangling endpoint binding")

    # 3. Auth: register roles that are used but undeclared; drop bad refs.
    if auth.get("enabled"):
        declared = set(auth.get("roles", []))
        used = set()
        for ep in api.get("endpoints", []):
            used.update(ep.get("allowed_roles", []))
        for perm in auth.get("permissions", []):
            used.add(perm.get("role"))
        missing = [r for r in used if r and r not in declared]
        if missing:
            auth.setdefault("roles", []).extend(missing)
            fixes.append(f"auth: registered roles {missing}")
        before = len(auth.get("permissions", []))
        auth["permissions"] = [
            p for p in auth.get("permissions", [])
            if table_name(p.get("entity", "")) in columns
        ]
        if len(auth["permissions"]) != before:
            fixes.append("auth: removed permissions with unknown entities")
        auth["premium_gated_entities"] = [
            e for e in auth.get("premium_gated_entities", [])
            if table_name(e) in columns
        ]

    return config, fixes


# --------------------------------------------------------------------------- #
# LLM repair (only for what determinism cannot fix)
# --------------------------------------------------------------------------- #
def _unwrap_layer(layer: str, payload: Dict) -> Dict:
    """Models sometimes wrap the layer, e.g. {"api": {...}}. Unwrap it."""
    if isinstance(payload, dict) and list(payload.keys()) == [layer]:
        return payload[layer]
    return payload


def repair_config(
    client: LLMClient,
    config: Dict,
    report: ValidationReport,
    max_attempts: int = 3,
) -> tuple[Dict, RepairTrace]:
    trace = RepairTrace()
    current = dict(config)

    # Pass 1: deterministic.
    current, fixes = deterministic_repair(current)
    trace.deterministic_fixes = fixes
    report = validate_config(current)

    # Pass 2: targeted LLM repair for whatever remains.
    for _ in range(max_attempts):
        if report.ok:
            break
        trace.llm_attempts += 1
        for layer in report.affected_layers():
            problems = [
                f"{i.code}: {i.message}" for i in report.errors if i.layer == layer
            ]
            system, user = prompts.repair_prompt(layer, current, problems)
            try:
                fixed = _unwrap_layer(layer, client.complete_json(system, user))
            except LLMError:
                continue
            current[layer] = fixed
            trace.layers_repaired.append(layer)
        # deterministic cleanup after each LLM pass, then re-validate
        current, _ = deterministic_repair(current)
        report = validate_config(current)

    trace.remaining_errors = [i.message for i in report.errors]
    return current, trace
