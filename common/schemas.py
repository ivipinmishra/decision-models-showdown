"""Normalized, vendor-neutral question and result shapes."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Literal

Kind = Literal["predicate", "choice", "score"]


@dataclass(frozen=True)
class Question:
    name: str
    kind: Kind
    instructions: str
    # choice: [(value, description)]; score: [(label, description)] ordered low -> high
    options: tuple[tuple[str, str], ...] = ()


@dataclass
class Answer:
    name: str
    kind: Kind
    # choice -> chosen value (str); predicate -> P(true); score -> probability-weighted level
    value: str | float
    # choice -> {value: p}; predicate -> {"true": p, "false": 1-p}; score -> {"0": p, "1": p, ...}
    distribution: dict[str, float]
    confidence: float | None = None  # neither vendor returns confidence for predicates


@dataclass
class ProviderResult:
    provider: str
    mode: Literal["live", "mock"]
    answers: dict[str, Answer] = field(default_factory=dict)
    latency_ms: float = 0.0
    cost_usd: float = 0.0
    cost_is_estimate: bool = False
    error: str | None = None
    model: str | None = None         # model/version the vendor reports back
    input_tokens: int | None = None  # as reported, or estimated (see cost_is_estimate)
    request: dict | None = None      # exact payload sent (vendor wire shape)
    raw: dict | None = None          # exact response received (vendor wire shape)

    def to_dict(self) -> dict:
        return asdict(self)
