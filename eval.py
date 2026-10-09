"""Evaluate both providers against hand-labeled samples.

    python eval.py --app tickets
    python eval.py --app alerts
    python eval.py --app tickets --mock      # force MOCK mode even if keys are set
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
from pathlib import Path

from common.providers import default_providers
from common.runner import run_all

ROOT = Path(__file__).parent
BUCKETS = [(0.0, 0.5), (0.5, 0.7), (0.7, 0.9), (0.9, 1.0001)]


def table(headers: list[str], rows: list[list]) -> str:
    cells = [headers] + [[str(c) for c in r] for r in rows]
    widths = [max(len(r[i]) for r in cells) for i in range(len(headers))]
    line = lambda r: "  ".join(c.ljust(w) for c, w in zip(r, widths))
    return "\n".join([line(cells[0]), "  ".join("-" * w for w in widths)] + [line(r) for r in cells[1:]])


def pctile(xs: list[float], q: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, round(q * (len(xs) - 1)))] if xs else 0.0


def pct(n: int, d: int) -> str:
    return f"{100 * n / d:.0f}%" if d else "–"


async def collect(app: str, samples: list[dict], key: str, questions, force_mock: bool):
    providers = default_providers(force_mock)
    rows = []
    for s in samples:
        results = await run_all(f"eval-{app}", s[key], questions, providers)
        rows.append((s, {r.provider: r for r in results}))
    return [p.name for p in providers], {p.name: p.mock for p in providers}, rows


def summary(names, modes, rows, primary: str, is_correct, extra_cols: dict):
    """Accuracy, agreement, latency, cost and calibration on the `primary` choice question."""
    if any(modes.values()):
        print("!! MOCK providers return hash-derived random probabilities. Their accuracy, latency and\n"
              "!! calibration numbers are meaningless: they test the harness, not the models.\n")
    out = []
    for n in names:
        res = [(s, r[n]) for s, r in rows]
        lat = [r.latency_ms for _, r in res]
        row = [f"{n} ({'MOCK' if modes[n] else 'live'})",
               pct(sum(is_correct(s, r) for s, r in res), len(res))]
        row += [pct(sum(f(s, r) for s, r in res), len(res)) for f in extra_cols.values()]
        row += [f"{statistics.median(lat):.0f}", f"{pctile(lat, 0.95):.0f}",
                f"${sum(r.cost_usd for _, r in res):.6f}" + ("*" if any(r.cost_is_estimate for _, r in res) else ""),
                sum(1 for _, r in res if r.error)]
        out.append(row)
    print(table(["provider", f"{primary} acc", *extra_cols, "p50 ms", "p95 ms", "total cost", "errors"], out))
    print("* cost estimated from ~4 chars/token (no usage reported)\n")

    a, b = names
    agree = sum(r[a].answers.get(primary) is not None and r[b].answers.get(primary) is not None
                and r[a].answers[primary].value == r[b].answers[primary].value for _, r in rows)
    print(f"Agreement on {primary} between {a} and {b}: {pct(agree, len(rows))} ({agree}/{len(rows)})\n")

    print(f"Calibration on {primary} confidence (accuracy per bucket):")
    cal = []
    for lo, hi in BUCKETS:
        row = [f"{lo:.1f}–{min(hi, 1):.1f}"]
        for n in names:
            hits = [is_correct(s, r[n]) for s, r in rows
                    if (c := getattr(r[n].answers.get(primary), "confidence", None)) is not None and lo <= c < hi]
            row.append(f"{pct(sum(hits), len(hits))} (n={len(hits)})")
        cal.append(row)
    print(table(["confidence", *names], cal) + "\n")


def eval_tickets(args):
    from tickets.questions import QUESTIONS
    from tickets.routing import SECURITY_THRESHOLD, route

    samples = json.loads((ROOT / "samples" / "tickets.json").read_text())
    names, modes, rows = asyncio.run(collect("tickets", samples, "text", QUESTIONS, args.mock))

    team_ok = lambda s, r: getattr(r.answers.get("team"), "value", None) == s["expected_team"]
    sec_ok = lambda s, r: (getattr(r.answers.get("security_sensitive"), "value", 0) > 0.5) == s["expected_security"]
    impact_ok = lambda s, r: round(getattr(r.answers.get("customer_impact"), "value", -9)) == s["expected_impact"]
    print(f"== Tickets: {len(samples)} samples ==\n")
    summary(names, modes, rows, "team", team_ok, {"security acc": sec_ok, "impact acc": impact_ok})

    print(f"Threshold sweep (security threshold fixed at {SECURITY_THRESHOLD}):")
    sweep = []
    for t in [0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95]:
        row = [f"{t:.2f}"]
        for n in names:
            routed = [(s, route(r[n], choice_threshold=t)) for s, r in rows]
            human = sum(d["queue"] == "human_review" for _, d in routed)
            sec = sum(d["queue"] == "security" for _, d in routed)
            mis = sum(d["queue"].startswith("team:") and d["queue"] != f"team:{s['expected_team']}"
                      for s, d in routed)
            row.append(f"human={human:<2} security={sec:<2} misrouted={mis}")
        sweep.append(row)
    print(table(["threshold", *names], sweep))


def eval_alerts(args):
    from alerts.questions import QUESTIONS
    from alerts.routing import route

    samples = json.loads((ROOT / "samples" / "alerts.json").read_text())
    names, modes, rows = asyncio.run(collect("alerts", samples, "alert", QUESTIONS, args.mock))

    model_ok = lambda s, r: getattr(r.answers.get("recommended_action"), "value", None) == s["expected_action"]
    code_ok = lambda s, r: route(r, s["alert"])["action"] == s["expected_action"]
    sev_ok = lambda s, r: round(getattr(r.answers.get("severity"), "value", -9)) == s["expected_severity"]
    dep_ok = lambda s, r: (getattr(r.answers.get("likely_caused_by_deploy"), "value", 0) > 0.5) == s["expected_deploy_cause"]
    print(f"== Alerts: {len(samples)} samples ==\n")
    summary(names, modes, rows, "recommended_action", model_ok,
            {"code-branch acc": code_ok, "severity acc": sev_ok, "deploy acc": dep_ok})


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--app", choices=["tickets", "alerts"], required=True)
    ap.add_argument("--mock", action="store_true", help="force MOCK mode for both providers")
    args = ap.parse_args()
    (eval_tickets if args.app == "tickets" else eval_alerts)(args)
