from common.schemas import Question

TEAMS = ("billing", "account_access", "bug_report", "feature_request", "integrations", "other")

QUESTIONS = [
    Question(
        "team", "choice",
        "Which TaskHarbor support team should own this ticket? Pick the team for the customer's main problem.",
        (
            ("billing", "Invoices, charges, refunds, plan or seat changes, payment methods"),
            ("account_access", "Login, SSO, 2FA, password reset, locked or deactivated accounts"),
            ("bug_report", "Something in TaskHarbor is broken, erroring, or behaving incorrectly"),
            ("feature_request", "Asking for new functionality or a change to how something works"),
            ("integrations", "Problems with connected apps, webhooks, the public API, or imports/exports"),
            ("other", "None of the above, or not a support request"),
        ),
    ),
    Question(
        "security_sensitive", "predicate",
        "The ticket mentions a possible account compromise, data exposure, or leaked credentials "
        "(e.g. unknown logins, shared API tokens, data visible to the wrong people).",
    ),
    Question(
        "customer_impact", "score",
        "How badly is the customer affected right now?",
        (
            ("none", "No impact; a question or suggestion"),
            ("inconvenience", "Annoying but they can keep working"),
            ("blocked_individual", "One person cannot do their work"),
            ("blocked_team", "A whole team or organization is blocked"),
        ),
    ),
]
