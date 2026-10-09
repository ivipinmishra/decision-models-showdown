from alerts.routing import route as route_alert
from common.schemas import Answer, ProviderResult
from tickets.routing import route as route_ticket


def result(*answers):
    return ProviderResult("test", "mock", {a.name: a for a in answers})


def team(value, conf):
    return Answer("team", "choice", value, {value: 1.0}, conf)


def pred(name, p):
    return Answer(name, "predicate", p, {"true": p, "false": 1 - p})


def sev(v):
    return Answer("severity", "score", v, {}, 0.9)


# ---- tickets
def test_confident_team_routes_to_team():
    d = route_ticket(result(team("billing", 0.9), pred("security_sensitive", 0.1)), 0.75, 0.5)
    assert d == {"queue": "team:billing", "escalated": False, "reasons": d["reasons"]}


def test_low_confidence_goes_to_human():
    assert route_ticket(result(team("billing", 0.6), pred("security_sensitive", 0.1)), 0.75, 0.5)["queue"] == "human_review"


def test_other_goes_to_human_even_if_confident():
    assert route_ticket(result(team("other", 0.99), pred("security_sensitive", 0.1)), 0.75, 0.5)["queue"] == "human_review"


def test_security_overrides_team():
    d = route_ticket(result(team("billing", 0.99), pred("security_sensitive", 0.7)), 0.75, 0.5)
    assert d["queue"] == "security" and d["escalated"]


def test_missing_team_answer_fails_safe():
    assert route_ticket(result(pred("security_sensitive", 0.1)))["queue"] == "human_review"


# ---- alerts
PROD = {"environment": "prod", "recent_deploy": True}


def test_score_thresholds_not_labels():
    # 1.55 is closest to label "degraded" (2) but is below the 1.6 page threshold
    assert route_alert(result(sev(1.55), pred("likely_caused_by_deploy", 0.1)), PROD)["action"] == "add_to_watchlist"
    assert route_alert(result(sev(1.6), pred("likely_caused_by_deploy", 0.1)), PROD)["action"] == "page_on_call"
    assert route_alert(result(sev(0.5), pred("likely_caused_by_deploy", 0.1)), PROD)["action"] == "ignore"


def test_rollback_needs_deploy_flag_and_probability():
    r = result(sev(2.5), pred("likely_caused_by_deploy", 0.9))
    assert route_alert(r, PROD)["action"] == "rollback_recent_deploy"
    assert route_alert(r, {**PROD, "recent_deploy": False})["action"] == "page_on_call"
    assert route_alert(result(sev(2.5), pred("likely_caused_by_deploy", 0.5)), PROD)["action"] == "page_on_call"


def test_staging_never_pages():
    d = route_alert(result(sev(3.0), pred("likely_caused_by_deploy", 0.95)), {**PROD, "environment": "staging"})
    assert d["action"] == "add_to_watchlist" and not d["escalated"]


def test_missing_severity_fails_safe():
    assert route_alert(result(), PROD)["action"] == "page_on_call"
