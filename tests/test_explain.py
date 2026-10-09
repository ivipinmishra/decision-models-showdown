from alerts.routing import route
from common.explain import explain
from common.schemas import Answer, ProviderResult

ALERT = {"environment": "prod", "recent_deploy": True}
decide = lambda r, alert, params: route(r, alert, **params)


def make(provider, sev, p_deploy, action, action_p):
    dist = {a: (action_p if a == action else (1 - action_p) / 3)
            for a in ("ignore", "add_to_watchlist", "page_on_call", "rollback_recent_deploy")}
    return ProviderResult(provider, "live", {
        "severity": Answer("severity", "score", sev, {"0": 0.1, "1": 0.9}, 0.8),
        "likely_caused_by_deploy": Answer("likely_caused_by_deploy", "predicate", p_deploy, {}),
        "recommended_action": Answer("recommended_action", "choice", action, dist, 0.4),
    })


def run(a, b):
    return explain([a, b], [decide(a, ALERT, {}), decide(b, ALERT, {})], ALERT, {}, decide)


def test_severity_is_identified_as_decisive():
    # the case from the screenshot: both deploy probabilities >= 0.7, severities either side of 1.6
    x = run(make("openai", 0.96, 0.75, "ignore", 0.72), make("typesafe", 1.89, 0.83, "rollback_recent_deploy", 0.99))
    assert not x["same_outcome"]
    assert [d["question"] for d in x["decisive"]] == ["severity"]
    assert x["decisive"][0]["after"] == "rollback_recent_deploy"
    assert {d["question"] for d in x["disagreements"]} == {"severity", "recommended_action"}


def test_model_recommendation_vs_code_consistency():
    x = run(make("openai", 0.96, 0.75, "ignore", 0.72), make("typesafe", 1.89, 0.83, "rollback_recent_deploy", 0.99))
    c = {c["provider"]: c for c in x["consistency"]}
    assert not c["openai"]["agrees"] and c["openai"]["code_says"] == "add_to_watchlist"
    assert c["typesafe"]["agrees"]


def test_same_outcome_has_nothing_decisive():
    x = run(make("openai", 2.5, 0.9, "rollback_recent_deploy", 0.9), make("typesafe", 2.2, 0.8, "page_on_call", 0.6))
    assert x["same_outcome"] and x["decisive"] == []
