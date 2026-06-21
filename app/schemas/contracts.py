"""Strict, typed contracts for every layer of the generated application.

These Pydantic models are the single source of truth for a valid output. Every
pipeline stage must produce data that parses into these models, and the
validator enforces cross-layer consistency on top of them.

Design choices:
- Closed vocabularies (enums) for types/methods so the model cannot invent
  field types -- a form of schema-constrained generation that aids determinism.
- `extra="forbid"` turns hallucinated/extra keys into hard errors, which is
  exactly what lets the repair engine detect and fix drift.
"""
from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ----- Stage 1: structured intent ----------------------------------------- #
class Intent(_Strict):
    app_name: str = Field(..., min_length=1)
    summary: str = Field(..., min_length=1)
    features: List[str] = Field(default_factory=list)
    entities: List[str] = Field(default_factory=list)
    roles: List[str] = Field(default_factory=list)
    has_auth: bool = False
    has_payments: bool = False
    assumptions: List[str] = Field(default_factory=list)
    open_questions: List[str] = Field(default_factory=list)


# ----- Stage 2: system design --------------------------------------------- #
class EntityDesign(_Strict):
    name: str = Field(..., min_length=1)
    description: str = ""
    owned_by_role: Optional[str] = None


class FlowDesign(_Strict):
    name: str
    steps: List[str] = Field(default_factory=list)


class SystemDesign(_Strict):
    entities: List[EntityDesign] = Field(default_factory=list)
    roles: List[str] = Field(default_factory=list)
    flows: List[FlowDesign] = Field(default_factory=list)
    premium_features: List[str] = Field(default_factory=list)


# ----- Stage 3: the four schemas ------------------------------------------ #
class FieldType(str, Enum):
    string = "string"
    integer = "integer"
    number = "number"
    boolean = "boolean"
    datetime = "datetime"
    text = "text"
    foreign_key = "foreign_key"


class DBColumn(_Strict):
    name: str = Field(..., min_length=1)
    type: FieldType
    primary_key: bool = False
    required: bool = False
    references: Optional[str] = None  # "table.column", only for foreign_key


class DBTable(_Strict):
    name: str = Field(..., min_length=1)
    columns: List[DBColumn] = Field(..., min_length=1)


class DBSchema(_Strict):
    tables: List[DBTable] = Field(default_factory=list)


class HTTPMethod(str, Enum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"


class APIField(_Strict):
    name: str
    type: FieldType
    required: bool = False


class APIEndpoint(_Strict):
    path: str = Field(..., pattern=r"^/.*")
    method: HTTPMethod
    entity: str = Field(..., min_length=1)
    description: str = ""
    request_fields: List[APIField] = Field(default_factory=list)
    response_fields: List[APIField] = Field(default_factory=list)
    allowed_roles: List[str] = Field(default_factory=list)


class APISchema(_Strict):
    endpoints: List[APIEndpoint] = Field(default_factory=list)


class UIComponentType(str, Enum):
    form = "form"
    table = "table"
    detail = "detail"
    dashboard = "dashboard"
    nav = "nav"


class UIComponent(_Strict):
    type: UIComponentType
    entity: Optional[str] = None
    fields: List[str] = Field(default_factory=list)
    bound_endpoint: Optional[str] = None  # "METHOD path"


class UIPage(_Strict):
    name: str = Field(..., min_length=1)
    path: str = Field(..., pattern=r"^/.*")
    components: List[UIComponent] = Field(default_factory=list)
    visible_to_roles: List[str] = Field(default_factory=list)


class UISchema(_Strict):
    pages: List[UIPage] = Field(default_factory=list)


class Permission(_Strict):
    role: str = Field(..., min_length=1)
    entity: str = Field(..., min_length=1)
    actions: List[HTTPMethod] = Field(default_factory=list)


class AuthSchema(_Strict):
    enabled: bool = False
    roles: List[str] = Field(default_factory=list)
    permissions: List[Permission] = Field(default_factory=list)
    premium_gated_entities: List[str] = Field(default_factory=list)


# ----- Final assembled application configuration -------------------------- #
class AppConfig(_Strict):
    app_name: str
    intent: Intent
    design: SystemDesign
    db: DBSchema
    api: APISchema
    ui: UISchema
    auth: AuthSchema
