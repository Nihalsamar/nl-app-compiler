"""Validation engine: structural (Pydantic) + cross-layer consistency.

Two layers of checking:
1. Structural -- does each layer parse into the strict Pydantic contract?
   (valid JSON, required fields, types, no hallucinated keys.)
2. Semantic / cross-layer -- do the layers agree with each other?
   * every API/UI entity has a DB table
   * UI components bind to endpoints that exist
   * UI fields map to API fields
   * API fields agree with DB column types
   * roles used in the API/permissions exist in auth

Each problem is reported as a ValidationIssue tagged with the `layer` that
should be regenerated, which is exactly what the repair engine consumes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from pydantic import ValidationError

from app.naming import table_name
from app.schemas.contracts import (
    APISchema,
    AuthSchema,
    DBSchema,
    Intent,
    SystemDesign,
    UISchema,
)


@dataclass
class ValidationIssue:
    layer: str          # "intent" | "design" | "db" | "api" | "ui" | "auth"
    code: str           # machine-readable failure type
    message: str        # human-readable detail
    severity: str = "error"  # "error" | "warning"


@dataclass
class ValidationReport:
    issues: List[ValidationIssue] = field(default_factory=list)

    @property
    def errors(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == "warning"]

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0

    def affected_layers(self) -> List[str]:
        seen: List[str] = []
        for i in self.errors:
            if i.layer not in seen:
                seen.append(i.layer)
        return seen

    def summary(self) -> str:
        if self.ok:
            return "valid"
        return "; ".join(f"[{i.layer}/{i.code}] {i.message}" for i in self.errors)


_STRUCTURAL = {
    "intent": Intent,
    "design": SystemDesign,
    "db": DBSchema,
    "api": APISchema,
    "ui": UISchema,
    "auth": AuthSchema,
}


def _structural_check(config: Dict) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    for layer, model in _STRUCTURAL.items():
        raw = config.get(layer)
        if raw is None:
            issues.append(ValidationIssue(layer, "missing_layer", f"'{layer}' layer is absent"))
            continue
        try:
            model.model_validate(raw)
        except ValidationError as exc:
            first = exc.errors()[0]
            loc = ".".join(str(p) for p in first.get("loc", []))
            issues.append(ValidationIssue(
                layer, "schema_violation",
                f"{loc or '<root>'}: {first.get('msg', 'invalid')}",
            ))
    return issues


def _semantic_check(config: Dict) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    db = config.get("db", {}) or {}
    api = config.get("api", {}) or {}
    ui = config.get("ui", {}) or {}
    auth = config.get("auth", {}) or {}

    tables = {t["name"]: t for t in db.get("tables", [])}
    columns_by_table = {
        name: {c["name"]: c for c in t.get("columns", [])}
        for name, t in tables.items()
    }

    # endpoint lookup keyed by "METHOD path"
    endpoint_keys = set()
    api_fields_by_entity: Dict[str, Dict[str, str]] = {}
    for ep in api.get("endpoints", []):
        endpoint_keys.add(f"{ep.get('method')} {ep.get('path')}")
        ent = ep.get("entity", "")
        tbl = table_name(ent)
        if tbl not in tables:
            issues.append(ValidationIssue(
                "api", "entity_without_table",
                f"endpoint {ep.get('method')} {ep.get('path')} targets entity "
                f"'{ent}' but table '{tbl}' does not exist",
            ))
        bucket = api_fields_by_entity.setdefault(ent, {})
        for f in ep.get("request_fields", []) + ep.get("response_fields", []):
            bucket[f["name"]] = f["type"]
            # API field vs DB column type agreement
            col = columns_by_table.get(tbl, {}).get(f["name"])
            if col and col["type"] != f["type"] and f["name"] != "id":
                issues.append(ValidationIssue(
                    "api", "field_type_mismatch",
                    f"entity '{ent}' field '{f['name']}' is '{f['type']}' in API "
                    f"but '{col['type']}' in DB table '{tbl}'",
                ))

    # UI references
    for page in ui.get("pages", []):
        for comp in page.get("components", []):
            be = comp.get("bound_endpoint")
            if be and be not in endpoint_keys:
                issues.append(ValidationIssue(
                    "ui", "dangling_endpoint",
                    f"component on page '{page.get('name')}' binds to '{be}' "
                    f"which is not a defined API endpoint",
                ))
            ent = comp.get("entity")
            if ent:
                known = api_fields_by_entity.get(ent, {})
                for fld in comp.get("fields", []):
                    if known and fld not in known:
                        issues.append(ValidationIssue(
                            "ui", "ui_field_not_in_api",
                            f"component on page '{page.get('name')}' uses field "
                            f"'{fld}' for entity '{ent}' not exposed by any API",
                        ))

    # Auth references
    if auth.get("enabled"):
        roles = set(auth.get("roles", []))
        for ep in api.get("endpoints", []):
            for r in ep.get("allowed_roles", []):
                if r not in roles:
                    issues.append(ValidationIssue(
                        "auth", "unknown_role",
                        f"endpoint {ep.get('method')} {ep.get('path')} allows role "
                        f"'{r}' not declared in auth.roles",
                    ))
        for perm in auth.get("permissions", []):
            tbl = table_name(perm.get("entity", ""))
            if tbl not in tables:
                issues.append(ValidationIssue(
                    "auth", "permission_unknown_entity",
                    f"permission references entity '{perm.get('entity')}' with no table",
                ))
        for ent in auth.get("premium_gated_entities", []):
            if table_name(ent) not in tables:
                issues.append(ValidationIssue(
                    "auth", "gated_unknown_entity",
                    f"premium_gated_entities references unknown entity '{ent}'",
                    severity="warning",
                ))
    return issues


def validate_config(config: Dict) -> ValidationReport:
    """Run structural then semantic checks. Semantic checks only run if the
    structure is sound enough to interpret."""
    report = ValidationReport()
    report.issues.extend(_structural_check(config))
    structural_layers = {i.layer for i in report.errors}
    # Only attempt cross-layer checks when the involved layers parsed.
    if not ({"db", "api", "ui", "auth"} & structural_layers):
        report.issues.extend(_semantic_check(config))
    return report
