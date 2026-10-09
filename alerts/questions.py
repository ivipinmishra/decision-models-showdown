from common.schemas import Question

ACTIONS = ("ignore", "add_to_watchlist", "page_on_call", "rollback_recent_deploy")

QUESTIONS = [
    Question(
        "severity", "score",
        "How severe is this monitoring alert, judging by the metric's deviation from baseline, "
        "duration, environment, and blast radius (dependent services)?",
        (
            ("noise", "Normal fluctuation or a non-production blip; nothing to do"),
            ("watch", "Unusual but not yet harming users; keep an eye on it"),
            ("degraded", "Service is measurably degraded for some users or dependents"),
            ("outage", "Customer-facing outage or severe, sustained degradation in production"),
        ),
    ),
    Question(
        "recommended_action", "choice",
        "What should the on-call engineer do about this alert right now?",
        (
            ("ignore", "No action needed"),
            ("add_to_watchlist", "Track it; re-check later"),
            ("page_on_call", "Wake up a human now"),
            ("rollback_recent_deploy", "Roll back the most recent deploy, it is the likely cause"),
        ),
    ),
    Question(
        "likely_caused_by_deploy", "predicate",
        "The anomaly was most likely caused by the recent deploy (it started shortly after a deploy "
        "and nothing else in the state explains it).",
    ),
]
