"""Project 1: TaskHarbor support ticket router. Mounted at /tickets/ by server.py."""
from pathlib import Path

from common.web import ROOT, make_app
from tickets.questions import QUESTIONS
from tickets.routing import route

app = make_app(
    "tickets",
    page=Path(__file__).with_name("index.html"),
    samples=ROOT / "samples" / "tickets.json",
    questions=QUESTIONS,
    decide=lambda result, _ticket, params: route(result, **params),
)
