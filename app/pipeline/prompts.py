"""Prompt construction for each pipeline stage.

Every system prompt carries a `stage=<name>` marker. The real model ignores it
as ordinary text; the mock client uses it to branch. Each prompt restates the
exact JSON contract so the model is constrained, and forbids prose so output is
parseable.

Schema generation is split into four narrow stages (db -> api -> ui -> auth).
Smaller responses fit well within token limits (no truncation) and each layer
is validated/repaired independently -- a more compiler-like, reliable design.
"""
from __future__ import annotations

import json

_JSON_RULES = (
    "Return ONLY a single valid JSON object. No markdown, no prose, no code "
    "fences. Use exactly the specified keys. Do not invent keys."
)

INTENT_SYSTEM = (
    "stage=intent\n"
    "You are the Intent Extraction stage of a software-generation compiler. "
    "Convert the user's natural-language request into a structured intent.\n"
    f"{_JSON_RULES}\n"
    "Schema: {app_name:str, summary:str, features:[str], entities:[str], "
    "roles:[str], has_auth:bool, has_payments:bool, assumptions:[str], "
    "open_questions:[str]}. entities are singular lowercase nouns and must NOT "
    "include roles like 'admin' or 'user' unless they are themselves data."
)

DESIGN_SYSTEM = (
    "stage=design\n"
    "You are the System Design stage. Given the intent, define the app "
    "architecture.\n"
    f"{_JSON_RULES}\n"
    "Schema: {entities:[{name:str, description:str, owned_by_role:str|null}], "
    "roles:[str], flows:[{name:str, steps:[str]}], premium_features:[str]}."
)

DB_SYSTEM = (
    "stage=db\n"
    "You are the Database Schema stage. For each design entity output one table "
    "named singularize(entity)+'s'. Always include an integer primary key 'id' "
    "and a 'created_at' datetime.\n"
    f"{_JSON_RULES}\n"
    "field type is one of: string,integer,number,boolean,datetime,text,foreign_key. "
    "For foreign_key set references to 'table.column'.\n"
    "Schema: {tables:[{name:str, columns:[{name:str, type, primary_key:bool, "
    "required:bool, references:str|null}]}]}."
)

API_SYSTEM = (
    "stage=api\n"
    "You are the API Schema stage. Generate REST endpoints whose entity maps to "
    "an existing DB table, with field names and types matching the DB columns.\n"
    f"{_JSON_RULES}\n"
    "method is one of GET,POST,PUT,DELETE. Provide list+create+update+delete per "
    "entity. allowed_roles must be roles from the design.\n"
    "Schema: {endpoints:[{path:str, method, entity:str, description:str, "
    "request_fields:[{name,type,required}], response_fields:[{name,type,required}], "
    "allowed_roles:[str]}]}."
)

UI_SYSTEM = (
    "stage=ui\n"
    "You are the UI Schema stage. Generate pages and components. Every component "
    "bound_endpoint must be one of the given API endpoints formatted 'METHOD /path', "
    "and every field must exist in that entity's API fields.\n"
    f"{_JSON_RULES}\n"
    "component type is one of form,table,detail,dashboard,nav.\n"
    "Schema: {pages:[{name:str, path:str, components:[{type, entity:str|null, "
    "fields:[str], bound_endpoint:str|null}], visible_to_roles:[str]}]}."
)

AUTH_SYSTEM = (
    "stage=auth\n"
    "You are the Auth Schema stage. Define roles and per-entity permissions. "
    "Every permission entity must be an existing table; every role must be "
    "declared in roles.\n"
    f"{_JSON_RULES}\n"
    "actions are a subset of GET,POST,PUT,DELETE.\n"
    "Schema: {enabled:bool, roles:[str], permissions:[{role:str, entity:str, "
    "actions:[str]}], premium_gated_entities:[str]}."
)


def intent_prompt(user_request: str) -> tuple[str, str]:
    return INTENT_SYSTEM, user_request.strip()


def design_prompt(intent: dict) -> tuple[str, str]:
    return DESIGN_SYSTEM, "Design the system.\n\n" + json.dumps({"intent": intent})


def db_prompt(intent: dict, design: dict) -> tuple[str, str]:
    return DB_SYSTEM, json.dumps({"intent": intent, "design": design})


def api_prompt(intent: dict, design: dict, db: dict) -> tuple[str, str]:
    return API_SYSTEM, json.dumps({"intent": intent, "design": design, "db": db})


def ui_prompt(intent: dict, design: dict, api: dict) -> tuple[str, str]:
    return UI_SYSTEM, json.dumps({"intent": intent, "design": design, "api": api})


def auth_prompt(intent: dict, design: dict, db: dict, api: dict) -> tuple[str, str]:
    return AUTH_SYSTEM, json.dumps(
        {"intent": intent, "design": design, "db": db, "api": api}
    )


def repair_prompt(layer: str, config: dict, issues: list[str]) -> tuple[str, str]:
    """Targeted repair: regenerate ONLY the broken layer, given the rest as
    fixed context plus the exact problems to fix."""
    system = (
        f"stage=repair:{layer}\n"
        "You are the Validation Repair stage of a software-generation compiler. "
        f"Regenerate ONLY the '{layer}' layer so that it satisfies the contract "
        "and resolves every listed problem. Keep everything already correct and "
        "do not change other layers.\n"
        f"{_JSON_RULES}\n"
        f"Return only the JSON object for the '{layer}' layer."
    )
    user = json.dumps({
        "problems_to_fix": issues,
        "current_config": config,
        "regenerate_layer": layer,
    })
    return system, user
