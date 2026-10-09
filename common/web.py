"""Tiny FastAPI factory shared by both apps: one HTML page, a samples endpoint, and /run."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .explain import explain
from .providers import default_providers
from .runner import run_all
from .schemas import ProviderResult, Question

ROOT = Path(__file__).resolve().parent.parent


class RunRequest(BaseModel):
    input: Any                      # ticket text (str) or alert object (dict)
    params: dict[str, float] = {}   # threshold overrides from the UI


def provider_status() -> dict:
    return {p.name: "mock" if p.mock else "live" for p in default_providers()}


def make_app(name: str, page: Path, samples: Path, questions: list[Question],
             decide: Callable[[ProviderResult, Any, dict], dict]) -> FastAPI:
    app = FastAPI(title=name)
    app.mount("/static", StaticFiles(directory=ROOT / "common" / "static"), name="static")

    @app.get("/", response_class=HTMLResponse)
    def index():
        return page.read_text()

    @app.get("/samples")
    def get_samples():
        return json.loads(samples.read_text())

    @app.get("/status")
    def status():
        return provider_status()

    @app.get("/questions")
    def get_questions():
        return [{"name": q.name, "kind": q.kind, "instructions": q.instructions,
                 "options": [{"value": v, "description": d} for v, d in q.options]} for q in questions]

    @app.post("/run")
    async def run(req: RunRequest):
        results = await run_all(name, req.input, questions)
        decisions = [decide(r, req.input, req.params) for r in results]
        return {"results": [{**r.to_dict(), "routing": d} for r, d in zip(results, decisions)],
                "explanation": explain(results, decisions, req.input, req.params, decide)}

    return app
