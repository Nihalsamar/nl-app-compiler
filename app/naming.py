"""Shared naming rules so every layer agrees on table names.

Keeping this in one place is what makes cross-layer consistency checkable:
an API entity "task" must map to DB table "tasks", deterministically.
"""
from __future__ import annotations


def singularize(word: str) -> str:
    if word.endswith("ies"):
        return word[:-3] + "y"
    if word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def table_name(entity: str) -> str:
    return singularize(entity.strip().lower()) + "s"
