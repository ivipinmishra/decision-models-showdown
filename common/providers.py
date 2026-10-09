"""DecisionProvider interface plus OpenAI Decisions and TypeSafe Jev implementations.

Each provider does three things:
  1. build_request(): normalized questions -> the vendor's documented wire shape
  2. call the vendor (or a deterministic MOCK that returns the same wire shape)
  3. normalize(): vendor wire shape -> common.schemas.Answer

Because MOCK mode emits the vendor's wire shape, the normalization code path is
the same in mock and live mode.
"""
from __future__ import annotations

import abc
import hashlib
import json
import math
import os
import random
import time
from typing import Any

from .schemas import Answer, ProviderResult, Question

# Published list prices (USD per 1M input tokens). Output tokens are free for both.
# OpenAI: developers.openai.com/api/docs/guides/decisions
# TypeSafe: typesafe.ai/blog/introducing-system-one-models-and-jev
OPENAI_INPUT_PER_M = 0.10
TYPESAFE_INPUT_PER_M = 0.042


def _estimate_tokens(payload: Any) -> int:
    """Rough ~4 chars/token estimate, used only when the API reports no usage (mock mode)."""
    return max(1, len(json.dumps(payload, default=str)) // 4)


def _fake_distribution(seed: str, n: int) -> list[float]:
    """Deterministic, moderately peaked distribution derived from a hash of the seed."""
    rng = random.Random(hashlib.sha256(seed.encode()).hexdigest())
    logits = [rng.gauss(0, 2.0) for _ in range(n)]
    m = max(logits)
    exps = [math.exp(x - m) for x in logits]
    total = sum(exps)
    return [round(e / total, 4) for e in exps]


def _peakedness(probs: list[float]) -> float:
    """1 - normalized entropy: 1 when all mass is on one outcome, 0 when uniform."""
    if len(probs) < 2:
        return 1.0
    h = -sum(p * math.log(p) for p in probs if p > 0)
    return round(1 - h / math.log(len(probs)), 4)


class DecisionProvider(abc.ABC):
    name: str
    api_key_env: str
    input_price_per_m: float

    def __init__(self, force_mock: bool = False):
        self.mock = force_mock or not os.getenv(self.api_key_env)

    async def decide(self, state: str | dict, questions: list[Question]) -> ProviderResult:
        request = self.build_request(state, questions)
        result = ProviderResult(provider=self.name, mode="mock" if self.mock else "live", request=request)
        start = time.perf_counter()
        try:
            raw = self.mock_response(request, questions) if self.mock else await self.call(request)
        except Exception as exc:  # surface vendor errors in the UI instead of crashing
            result.error = f"{type(exc).__name__}: {exc}"
            result.latency_ms = (time.perf_counter() - start) * 1000
            return result
        result.latency_ms = round((time.perf_counter() - start) * 1000, 1)
        result.raw, result.model = raw, raw.get("model")

        result.answers, refusals = self.normalize(raw, questions)
        if refusals:
            result.error = "refused: " + ", ".join(refusals)

        tokens = (raw.get("usage") or {}).get("input_tokens")
        result.cost_is_estimate = tokens is None
        tokens = tokens if tokens is not None else _estimate_tokens(request)
        result.input_tokens = tokens
        result.cost_usd = tokens * self.input_price_per_m / 1_000_000
        return result

    @abc.abstractmethod
    def build_request(self, state: str | dict, questions: list[Question]) -> dict: ...

    @abc.abstractmethod
    async def call(self, request: dict) -> dict: ...

    @abc.abstractmethod
    def mock_response(self, request: dict, questions: list[Question]) -> dict: ...

    @abc.abstractmethod
    def normalize(self, raw: dict, questions: list[Question]) -> tuple[dict[str, Answer], list[str]]: ...


# --------------------------------------------------------------------------- OpenAI
class OpenAIProvider(DecisionProvider):
    """POST /v1/decisions, model gpt-6-luna. Requires openai>=3.26.0."""

    name = "openai"
    api_key_env = "OPENAI_API_KEY"
    model = "gpt-6-luna"
    input_price_per_m = OPENAI_INPUT_PER_M

    def build_request(self, state, questions):
        # The Decisions API takes text (or messages); structured state is serialized to JSON text.
        text = state if isinstance(state, str) else json.dumps(state, indent=2)
        qs = []
        for q in questions:
            item: dict[str, Any] = {"type": q.kind, "name": q.name, "instructions": q.instructions}
            if q.kind == "choice":
                item["choices"] = [{"value": v, "description": d} for v, d in q.options]
            elif q.kind == "score":
                item["levels"] = [{"label": lbl, "description": d} for lbl, d in q.options]
            qs.append(item)
        return {"model": self.model, "input": text, "questions": qs}

    async def call(self, request):
        from openai import AsyncOpenAI

        async with AsyncOpenAI() as client:
            resp = await client.decisions.create(**request)
        return resp.model_dump()

    def mock_response(self, request, questions):
        answers = []
        for q in questions:
            seed = f"openai|{request['input']}|{q.name}"
            if q.kind == "predicate":
                answers.append({"type": "predicate", "name": q.name,
                                "probability": _fake_distribution(seed, 2)[0]})
                continue
            probs = _fake_distribution(seed, len(q.options))
            conf = _peakedness(probs)
            if q.kind == "choice":
                top = max(range(len(probs)), key=probs.__getitem__)
                answers.append({"type": "choice", "name": q.name, "choice": q.options[top][0],
                                "probabilities": [{"value": v, "probability": p}
                                                  for (v, _), p in zip(q.options, probs)],
                                "confidence": conf})
            else:
                answers.append({"type": "score", "name": q.name,
                                "score": round(sum(i * p for i, p in enumerate(probs)), 4),
                                "probabilities": [{"value": i, "label": lbl, "probability": p}
                                                  for i, ((lbl, _), p) in enumerate(zip(q.options, probs))],
                                "confidence": conf})
        return {"model": self.model, "answers": answers}  # no usage -> cost is estimated

    def normalize(self, raw, questions):
        out, refusals = {}, []
        for a in raw.get("answers", []):
            t, name = a.get("type"), a.get("name")
            if t == "refusal":
                refusals.append(name)
            elif t == "predicate":
                p = float(a["probability"])
                out[name] = Answer(name, "predicate", p, {"true": p, "false": round(1 - p, 4)})
            elif t == "choice":
                dist = {d["value"]: float(d["probability"]) for d in a["probabilities"]}
                out[name] = Answer(name, "choice", a["choice"], dist, a.get("confidence"))
            elif t == "score":
                dist = {str(d["value"]): float(d["probability"]) for d in a["probabilities"]}
                out[name] = Answer(name, "score", float(a["score"]), dist, a.get("confidence"))
        return out, refusals


# --------------------------------------------------------------------------- TypeSafe
class TypeSafeProvider(DecisionProvider):
    """POST https://api.typesafe.ai/v1/systemone, model jev-latest, via typesafe-sdk."""

    name = "typesafe"
    api_key_env = "TYPESAFE_API_KEY"
    model = "jev-latest"
    input_price_per_m = TYPESAFE_INPUT_PER_M

    def build_request(self, state, questions):
        # Jev accepts structured state directly: dicts are passed as JSON objects, not text.
        qs = {}
        for q in questions:
            if q.kind == "predicate":  # TypeSafe calls a yes/no question a "noul"
                qs[q.name] = {"type": "noul", "instructions": q.instructions}
            elif q.kind == "choice":
                qs[q.name] = {"type": "choice", "instructions": q.instructions,
                              "criteria": {v: d for v, d in q.options}}
            else:
                qs[q.name] = {"type": "score", "instructions": q.instructions,
                              "criteria": [f"{lbl}: {d}" for lbl, d in q.options]}
        return {"model": self.model, "state": state, "questions": qs}

    async def call(self, request):
        from typesafe_sdk import AsyncTypeSafeClient

        async with AsyncTypeSafeClient() as client:
            resp = await client.system_one(request["state"], request["questions"], model=request["model"])
        return {
            "model": resp.model,
            "answers": {k: v.model_dump() for k, v in resp.answers.items()},
            "usage": {"input_tokens": resp.usage.input_tokens, "output_tokens": resp.usage.output_tokens},
        }

    def mock_response(self, request, questions):
        state_key = json.dumps(request["state"], sort_keys=True, default=str)
        answers = {}
        for q in questions:
            seed = f"typesafe|{state_key}|{q.name}"
            if q.kind == "predicate":
                answers[q.name] = {"type": "noul", "noul": _fake_distribution(seed, 2)[0]}
                continue
            probs = _fake_distribution(seed, len(q.options))
            conf = _peakedness(probs)
            if q.kind == "choice":
                top = max(range(len(probs)), key=probs.__getitem__)
                answers[q.name] = {"type": "choice", "choice": q.options[top][0], "confidence": conf,
                                   "probabilities": {v: p for (v, _), p in zip(q.options, probs)}}
            else:
                answers[q.name] = {"type": "score", "confidence": conf,
                                   "score": round(sum(i * p for i, p in enumerate(probs)), 4),
                                   "legend": {str(i): lbl for i, (lbl, _) in enumerate(q.options)},
                                   "probabilities": {str(i): p for i, p in enumerate(probs)}}
        return {"model": "jev-mock", "answers": answers}  # no usage -> cost is estimated

    def normalize(self, raw, questions):
        out = {}
        for name, a in raw.get("answers", {}).items():
            t = a.get("type")
            if t == "noul":
                p = float(a["noul"])
                out[name] = Answer(name, "predicate", p, {"true": p, "false": round(1 - p, 4)})
            elif t == "choice":
                dist = {k: float(v) for k, v in a["probabilities"].items()}
                out[name] = Answer(name, "choice", a["choice"], dist, a.get("confidence"))
            elif t == "score":  # SDK keys levels by int, HTTP API by string: normalize to str
                dist = {str(k): float(v) for k, v in a["probabilities"].items()}
                out[name] = Answer(name, "score", float(a["score"]), dist, a.get("confidence"))
        return out, []


def default_providers(force_mock: bool = False) -> list[DecisionProvider]:
    return [OpenAIProvider(force_mock), TypeSafeProvider(force_mock)]
