"""Explain why two providers led to different outcomes.

Neither API returns a rationale, only probabilities and confidence. So "why" is built from
what we can observe:
  1. Counterfactual swaps: put one provider's answer into the other's result and re-run the
     routing code. If the outcome flips, that answer is decisive.
  2. Where the distributions split: top options, margins and confidence for each answer.
  3. Self-consistency: does a model's own recommendation match what your code derived from
     that same model's other answers?
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any, Callable

from .schemas import Answer, ProviderResult

LOW_CONFIDENCE = 0.5  # TypeSafe's docs suggest not acting below ~0.5


def outcome(decision: dict) -> str:
    return decision.get("queue") or decision.get("action")


def _top(a: Answer, n: int = 2) -> list[tuple[str, float]]:
    return sorted(a.distribution.items(), key=lambda kv: -kv[1])[:n]


def describe(a: Answer | None) -> dict:
    if a is None:
        return {"text": "no answer"}
    if a.kind == "predicate":
        return {"text": f"P(true) = {a.value:.2f}", "top": [], "confidence": None}
    top = _top(a)
    if a.kind == "choice":
        text = f"{a.value} at {top[0][1]:.0%}" + (f", runner-up {top[1][0]} at {top[1][1]:.0%}" if len(top) > 1 else "")
    else:
        text = f"expected {a.value:.2f}; most likely level {top[0][0]} at {top[0][1]:.0%}"
    return {"text": text, "top": top, "confidence": a.confidence,
            "low_confidence": a.confidence is not None and a.confidence < LOW_CONFIDENCE}


def _differs(x: Answer | None, y: Answer | None) -> bool:
    if x is None or y is None:
        return x is not y
    if x.kind == "choice":
        return x.value != y.value
    if x.kind == "predicate":
        return (x.value >= 0.5) != (y.value >= 0.5)
    return abs(x.value - y.value) >= 0.5


def explain(results: list[ProviderResult], decisions: list[dict], state: Any, params: dict,
            decide: Callable[[ProviderResult, Any, dict], dict]) -> dict:
    a, b = results
    oa, ob = outcome(decisions[0]), outcome(decisions[1])
    names = list(dict.fromkeys([*a.answers, *b.answers]))

    # 1. which single answer, swapped across providers, flips the code's decision?
    decisive = []
    if oa != ob:
        for q in names:
            for src, dst, target in ((b, a, ob), (a, b, oa)):
                if q not in src.answers:
                    continue
                swapped = replace(dst, answers={**dst.answers, q: src.answers[q]})
                new = outcome(decide(swapped, state, params))
                if new == target:
                    decisive.append({"question": q, "into": dst.provider, "from": src.provider,
                                     "value": src.answers[q].value, "before": outcome(decide(dst, state, params)),
                                     "after": new})
                    break

    # 2. where the model answers disagree
    disagreements = [{"question": q, "kind": (a.answers.get(q) or b.answers.get(q)).kind,
                      a.provider: describe(a.answers.get(q)), b.provider: describe(b.answers.get(q))}
                     for q in names if _differs(a.answers.get(q), b.answers.get(q))]

    # 3. does a choice answer recommend the same thing the code derived? (e.g. recommended_action)
    consistency = []
    for r, d in ((a, decisions[0]), (b, decisions[1])):
        for q, ans in r.answers.items():
            if ans.kind == "choice" and outcome(d) in ans.distribution:
                consistency.append({"provider": r.provider, "question": q, "model_says": ans.value,
                                    "code_says": outcome(d), "agrees": ans.value == outcome(d),
                                    "p_code_choice": ans.distribution[outcome(d)]})

    return {"same_outcome": oa == ob, "outcomes": {a.provider: oa, b.provider: ob},
            "any_mock": a.mode == "mock" or b.mode == "mock",
            "decisive": decisive, "disagreements": disagreements, "consistency": consistency}
