import asyncio
import sqlite3

import pytest

from common.providers import OpenAIProvider, TypeSafeProvider
from common.runner import run_all
from common.schemas import Question
from tickets.questions import QUESTIONS as TICKET_QS

QS = [
    Question("ok", "predicate", "Is it ok?"),
    Question("dept", "choice", "Which dept?", (("billing", "money"), ("technical", "bugs"), ("sales", "deals"))),
    Question("mood", "score", "How upset?", (("calm", ""), ("frustrated", ""), ("angry", ""))),
]


def test_openai_request_shape():
    req = OpenAIProvider(force_mock=True).build_request({"a": 1}, QS)
    assert req["model"] == "gpt-6-luna"
    assert isinstance(req["input"], str)  # structured state serialized to text
    assert req["questions"][1]["choices"][0] == {"value": "billing", "description": "money"}
    assert req["questions"][2]["levels"][1] == {"label": "frustrated", "description": ""}


def test_typesafe_request_shape():
    req = TypeSafeProvider(force_mock=True).build_request({"a": 1}, QS)
    assert req["model"] == "jev-latest"
    assert req["state"] == {"a": 1}  # structured state passed through as JSON
    assert req["questions"]["ok"]["type"] == "noul"
    assert req["questions"]["dept"]["criteria"] == {"billing": "money", "technical": "bugs", "sales": "deals"}
    assert len(req["questions"]["mood"]["criteria"]) == 3


def test_normalize_openai_documented_shape():
    raw = {"answers": [
        {"type": "predicate", "name": "ok", "probability": 0.8},
        {"type": "choice", "name": "dept", "choice": "billing", "confidence": 0.81,
         "probabilities": [{"value": "billing", "probability": 0.88}, {"value": "technical", "probability": 0.12},
                           {"value": "sales", "probability": 0.0}]},
        {"type": "score", "name": "mood", "score": 1.05, "confidence": 0.92,
         "probabilities": [{"value": 0, "label": "calm", "probability": 0.0},
                           {"value": 1, "label": "frustrated", "probability": 0.95},
                           {"value": 2, "label": "angry", "probability": 0.05}]},
        {"type": "refusal", "name": "other"},
    ]}
    answers, refusals = OpenAIProvider(force_mock=True).normalize(raw, QS)
    assert answers["ok"].value == 0.8 and answers["ok"].confidence is None
    assert answers["ok"].distribution == {"true": 0.8, "false": 0.2}
    assert answers["dept"].value == "billing" and answers["dept"].distribution["technical"] == 0.12
    assert answers["mood"].value == 1.05 and answers["mood"].distribution == {"0": 0.0, "1": 0.95, "2": 0.05}
    assert refusals == ["other"]


def test_normalize_typesafe_documented_shape():
    # Example payloads from docs.typesafe.ai/api, combined into one response.
    raw = {"model": "jev-1.13.0", "answers": {
        "ok": {"type": "noul", "noul": 0.95},
        "dept": {"type": "choice", "choice": "billing", "confidence": 0.81,
                 "probabilities": {"billing": 0.88, "technical": 0.12, "sales": 0.0}},
        "mood": {"type": "score", "score": 1.05, "confidence": 0.92,
                 "legend": {"0": "Calm", "1": "Frustrated", "2": "Very angry"},
                 "probabilities": {0: 0.0, 1: 0.95, 2: 0.05}},  # SDK uses int keys
    }, "usage": {"input_tokens": 318, "output_tokens": 34}}
    answers, _ = TypeSafeProvider(force_mock=True).normalize(raw, QS)
    assert answers["ok"].kind == "predicate" and answers["ok"].value == 0.95
    assert answers["dept"].confidence == 0.81
    assert answers["mood"].distribution == {"0": 0.0, "1": 0.95, "2": 0.05}


@pytest.mark.parametrize("cls", [OpenAIProvider, TypeSafeProvider])
def test_mock_is_deterministic_and_well_formed(cls):
    p = cls()  # no key in env -> mock
    assert p.mock
    r1 = asyncio.run(p.decide("my ticket", QS))
    r2 = asyncio.run(p.decide("my ticket", QS))
    assert r1.mode == "mock" and r1.error is None
    assert {k: a.value for k, a in r1.answers.items()} == {k: a.value for k, a in r2.answers.items()}
    for a in r1.answers.values():
        assert abs(sum(a.distribution.values()) - 1) < 1e-3
        if a.kind == "choice":
            assert a.value == max(a.distribution, key=a.distribution.get)
        if a.kind == "score":
            ev = sum(int(k) * p for k, p in a.distribution.items())
            assert abs(a.value - ev) < 1e-3 and 0 <= a.value <= 2
    assert r1.cost_usd > 0 and r1.cost_is_estimate


def test_run_all_parallel_and_logged(temp_db):
    results = asyncio.run(run_all("tickets", "I was double charged", TICKET_QS))
    assert [r.provider for r in results] == ["openai", "typesafe"]
    rows = sqlite3.connect(temp_db).execute("SELECT provider, mode, input_hash FROM calls").fetchall()
    assert len(rows) == 2 and rows[0][1] == "mock" and rows[0][2] == rows[1][2]


def test_vendor_error_is_captured():
    class Broken(OpenAIProvider):
        async def call(self, request):
            raise RuntimeError("boom")
    p = Broken()
    p.mock = False
    r = asyncio.run(p.decide("x", QS))
    assert r.error == "RuntimeError: boom" and r.answers == {}
