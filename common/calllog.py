"""Append-only SQLite log of every provider call."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time

from .schemas import ProviderResult

DB_PATH = os.getenv("DECISIONS_DB", "decisions_log.sqlite")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS calls (
    ts REAL, app TEXT, provider TEXT, mode TEXT, input_hash TEXT,
    answers TEXT, latency_ms REAL, cost_usd REAL, error TEXT
)"""


def input_hash(state) -> str:
    return hashlib.sha256(json.dumps(state, sort_keys=True, default=str).encode()).hexdigest()[:16]


def log_call(app: str, state, result: ProviderResult, db_path: str | None = None) -> None:
    answers = {k: {"value": a.value, "confidence": a.confidence} for k, a in result.answers.items()}
    with sqlite3.connect(db_path or DB_PATH) as conn:
        conn.execute(_SCHEMA)
        conn.execute(
            "INSERT INTO calls VALUES (?,?,?,?,?,?,?,?,?)",
            (time.time(), app, result.provider, result.mode, input_hash(state),
             json.dumps(answers), result.latency_ms, result.cost_usd, result.error),
        )
