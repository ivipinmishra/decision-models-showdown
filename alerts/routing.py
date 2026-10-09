"""Alert branch selection. Uses thresholds on the probability-weighted severity, not the raw label.

severity.value is an expected value over levels 0..3 (sum of level * probability), so 1.1 means
"mostly watch, a little degraded", not a category. Thresholds below cut that continuous value.
"""
from __future__ import annotations

import os

from common.schemas import ProviderResult

PAGE_SEVERITY = float(os.getenv("ALERTS_PAGE_SEVERITY", "1.6"))
WATCH_SEVERITY = float(os.getenv("ALERTS_WATCH_SEVERITY", "0.7"))
ROLLBACK_DEPLOY_P = float(os.getenv("ALERTS_ROLLBACK_DEPLOY_P", "0.7"))


def route(result: ProviderResult, alert: dict,
          page_severity: float = PAGE_SEVERITY,
          watch_severity: float = WATCH_SEVERITY,
          rollback_deploy_p: float = ROLLBACK_DEPLOY_P) -> dict:
    sev = result.answers.get("severity")
    deploy = result.answers.get("likely_caused_by_deploy")
    model_action = result.answers.get("recommended_action")
    if sev is None:
        return {"action": "page_on_call", "escalated": True,
                "reasons": ["no severity answer: fail safe to a human"]}

    s, p_deploy = float(sev.value), float(deploy.value) if deploy else 0.0
    reasons = [f"expected severity {s:.2f}"]

    if s >= page_severity and alert.get("recent_deploy") and p_deploy >= rollback_deploy_p:
        action = "rollback_recent_deploy"
        reasons.append(f"≥ {page_severity}, recent deploy, P(deploy cause)={p_deploy:.2f} ≥ {rollback_deploy_p}")
    elif s >= page_severity:
        action = "page_on_call"
        reasons.append(f"≥ page threshold {page_severity}")
    elif s >= watch_severity:
        action = "add_to_watchlist"
        reasons.append(f"≥ watch threshold {watch_severity}")
    else:
        action = "ignore"
        reasons.append(f"< watch threshold {watch_severity}")

    # Policy lives in code: staging never pages or rolls back automatically.
    if alert.get("environment") == "staging" and action in ("page_on_call", "rollback_recent_deploy"):
        action = "add_to_watchlist"
        reasons.append("staging policy: capped at add_to_watchlist")

    if model_action is not None and model_action.value != action:
        reasons.append(f"note: model recommended {model_action.value}")
    return {"action": action, "escalated": action in ("page_on_call", "rollback_recent_deploy"),
            "reasons": reasons}
