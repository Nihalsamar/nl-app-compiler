"""Minimal runtime that executes a validated AppConfig.

This is the "execution awareness" proof: instead of just claiming the config
is usable, we instantiate an in-memory CRUD application from it and run a smoke
test (create -> list -> update -> delete) against every entity. If any entity
cannot be exercised, the config is not truly executable and we say so.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from app.naming import table_name


class RuntimeError_(Exception):
    pass


class RuntimeApp:
    def __init__(self, config: Dict) -> None:
        self.config = config
        self.tables: Dict[str, List[Dict[str, Any]]] = {}
        self._counters: Dict[str, int] = {}
        self._columns: Dict[str, Dict[str, Dict]] = {}
        for t in config.get("db", {}).get("tables", []):
            self.tables[t["name"]] = []
            self._counters[t["name"]] = 0
            self._columns[t["name"]] = {c["name"]: c for c in t["columns"]}

    # --- core CRUD ------------------------------------------------------- #
    def _table_for(self, entity: str) -> str:
        tbl = table_name(entity)
        if tbl not in self.tables:
            raise RuntimeError_(f"no table for entity '{entity}'")
        return tbl

    def create(self, entity: str, data: Dict[str, Any]) -> Dict[str, Any]:
        tbl = self._table_for(entity)
        cols = self._columns[tbl]
        record: Dict[str, Any] = {}
        for name, col in cols.items():
            if col.get("primary_key"):
                self._counters[tbl] += 1
                record[name] = self._counters[tbl]
            elif col["type"] == "datetime":
                record[name] = datetime.now(timezone.utc).isoformat()
            elif name in data:
                record[name] = data[name]
            elif col.get("required") and not col.get("primary_key"):
                # required, not supplied, no default we can synthesise
                if col["type"] == "foreign_key":
                    record[name] = 1  # smoke-test owner
                else:
                    raise RuntimeError_(
                        f"missing required field '{name}' for '{entity}'"
                    )
        self.tables[tbl].append(record)
        return record

    def list(self, entity: str) -> List[Dict[str, Any]]:
        return list(self.tables[self._table_for(entity)])

    def update(self, entity: str, rec_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        tbl = self._table_for(entity)
        for rec in self.tables[tbl]:
            if rec.get("id") == rec_id:
                rec.update({k: v for k, v in data.items() if k in self._columns[tbl]})
                return rec
        raise RuntimeError_(f"{entity} id={rec_id} not found")

    def delete(self, entity: str, rec_id: int) -> bool:
        tbl = self._table_for(entity)
        before = len(self.tables[tbl])
        self.tables[tbl] = [r for r in self.tables[tbl] if r.get("id") != rec_id]
        return len(self.tables[tbl]) < before

    # --- sample data synthesis (for the execution proof) ---------------- #
    @staticmethod
    def _sample_value(col: dict):
        t = col["type"]
        name = col["name"]
        if t in ("string",):
            return f"sample {name}"
        if t == "text":
            return "sample text"
        if t == "integer":
            return 1
        if t == "number":
            return 1.0
        if t == "boolean":
            return True
        if t == "foreign_key":
            return 1
        return "sample"

    def _sample_record(self, tbl: str) -> Dict[str, Any]:
        """Build a complete, valid payload for every writable column so the
        smoke test exercises real schemas (email, role, etc.), not just name."""
        data: Dict[str, Any] = {}
        for name, col in self._columns[tbl].items():
            if col.get("primary_key") or col["type"] == "datetime":
                continue  # synthesised inside create()
            data[name] = self._sample_value(col)
        return data

    # --- execution proof ------------------------------------------------- #
    def smoke_test(self) -> Dict[str, Any]:
        """Exercise every entity end-to-end. Returns a per-entity report."""
        results = []
        entities = {ep["entity"] for ep in self.config.get("api", {}).get("endpoints", [])}
        all_ok = True
        for entity in sorted(entities):
            row = {"entity": entity, "ok": True, "error": None}
            try:
                tbl = self._table_for(entity)
                created = self.create(entity, self._sample_record(tbl))
                listed = self.list(entity)
                self.update(entity, created["id"], {"name": "updated"})
                deleted = self.delete(entity, created["id"])
                if not (created and listed and deleted):
                    raise RuntimeError_("CRUD cycle incomplete")
            except Exception as exc:  # noqa: BLE001 - report, don't crash
                row["ok"] = False
                row["error"] = str(exc)
                all_ok = False
            results.append(row)
        return {"executable": all_ok, "entities": results}
