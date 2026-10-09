"""One server for both projects.  Run: uvicorn server:app --port 8000  ->  http://localhost:8000"""
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from alerts.app import app as alerts_app
from common.web import ROOT, provider_status
from tickets.app import app as tickets_app

app = FastAPI(title="Decision Models Showdown")
app.mount("/static", StaticFiles(directory=ROOT / "common" / "static"), name="static")


@app.get("/", response_class=HTMLResponse)
def home():
    return (ROOT / "common" / "home.html").read_text()


@app.get("/status")
def status():
    return provider_status()


# /tickets and /alerts without a trailing slash would break the pages' relative URLs
@app.get("/tickets", include_in_schema=False)
def tickets_slash():
    return RedirectResponse("/tickets/")


@app.get("/alerts", include_in_schema=False)
def alerts_slash():
    return RedirectResponse("/alerts/")


app.mount("/tickets", tickets_app)
app.mount("/alerts", alerts_app)
