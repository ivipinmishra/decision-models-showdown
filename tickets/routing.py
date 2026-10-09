"""Routing is plain code. The model answers narrow questions; this file decides what happens."""
from __future__ import annotations

import os

from common.schemas import ProviderResult

CHOICE_CONFIDENCE_THRESHOLD = float(os.getenv("TICKETS_CHOICE_THRESHOLD", "0.75"))
SECURITY_THRESHOLD = float(os.getenv("TICKETS_SECURITY_THRESHOLD", "0.5"))


def route(result: ProviderResult,
          choice_threshold: float = CHOICE_CONFIDENCE_THRESHOLD,
          security_threshold: float = SECURITY_THRESHOLD) -> dict:
    team = result.answers.get("team")
    sec = result.answers.get("security_sensitive")
    reasons: list[str] = []

    # Security overrides everything, regardless of team.
    if sec is not None and sec.value > security_threshold:
        reasons.append(f"P(security_sensitive)={sec.value:.2f} > {security_threshold}")
        return {"queue": "security", "escalated": True, "reasons": reasons}

    if team is None:
        reasons.append("no team answer (error or refusal)")
    elif team.value == "other":
        reasons.append("team == other")
    elif team.confidence is None or team.confidence < choice_threshold:
        reasons.append(f"team confidence {team.confidence or 0:.2f} < {choice_threshold}")

    if reasons:
        return {"queue": "human_review", "escalated": True, "reasons": reasons}
    return {"queue": f"team:{team.value}", "escalated": False,
            "reasons": [f"team={team.value} at confidence {team.confidence:.2f}"]}
