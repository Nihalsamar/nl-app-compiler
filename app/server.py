"""FastAPI server exposing the generation compiler.

Endpoints:
  GET  /            -> the web UI
  POST /api/generate -> {prompt} -> full result (config, metrics, validation,
                        runtime smoke test)
  GET  /api/health  -> provider/health info
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.config import settings
from app.pipeline.orchestrator import generate_app
from app.runtime.engine import RuntimeApp
from app.validation.validator import validate_config

app = FastAPI(title="NL -> App Generation Compiler")

_STATIC = Path(__file__).parent / "static"


class GenerateRequest(BaseModel):
    prompt: str


@app.get("/")
def index() -> FileResponse:
    return FileResponse(_STATIC / "index.html")


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "provider": settings.provider, "model": settings.model}


@app.post("/api/generate")
def generate(req: GenerateRequest) -> dict:
    result = generate_app(req.prompt)
    payload = result.to_dict()

    # Attach validation detail + a live execution proof when we have a config.
    if result.config:
        report = validate_config(result.config)
        payload["validation"] = {
            "ok": report.ok,
            "errors": [
                {"layer": i.layer, "code": i.code, "message": i.message}
                for i in report.errors
            ],
            "warnings": [
                {"layer": i.layer, "code": i.code, "message": i.message}
                for i in report.warnings
            ],
        }
        try:
            payload["runtime"] = RuntimeApp(result.config).smoke_test()
        except Exception as exc:  # noqa: BLE001
            payload["runtime"] = {"executable": False, "error": str(exc)}
    return payload
