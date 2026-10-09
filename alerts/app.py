"""Project 2: Cloud alert triage. Mounted at /alerts/ by server.py."""
from pathlib import Path

from alerts.questions import QUESTIONS
from alerts.routing import route
from common.web import ROOT, make_app

app = make_app(
    "alerts",
    page=Path(__file__).with_name("index.html"),
    samples=ROOT / "samples" / "alerts.json",
    questions=QUESTIONS,
    decide=lambda result, alert, params: route(result, alert, **params),
)
