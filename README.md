# Decision Models Showdown

Compare two "decision model" APIs side by side on the same questions:

- **OpenAI Decisions**: model `gpt-6-luna`, `POST /v1/decisions`
- **TypeSafe Jev** (System One model): model `jev-latest`, `POST https://api.typesafe.ai/v1/systemone`

Both answer typed questions (yes/no, pick one, rate on a scale) with **probabilities instead of prose**. This project sends identical questions to both in parallel. Plain code then makes the final decision, using thresholds you control.

It contains **two projects** in one web app:

| | Project 1 · Support Ticket Router | Project 2 · Cloud Alert Triage |
|---|---|---|
| Input | Free-text ticket for *TaskHarbor* (a fictional SaaS) | A JSON monitoring alert (structured program state) |
| Questions | `team` (choice) · `security_sensitive` (yes/no) · `customer_impact` (score 0–3) | `severity` (score 0–3) · `recommended_action` (choice) · `likely_caused_by_deploy` (yes/no) |
| Code decides | team queue · security queue · human review | ignore · watchlist · page on-call · rollback |
| Samples | 20 hand-labeled tickets | 15 hand-labeled alerts |

> **No keys? It still works.** Any provider without an API key runs in clearly labeled **MOCK** mode with deterministic fake probabilities. Use it to explore the UI, but mock numbers mean nothing about the models.

---

## Contents

1. [Prerequisites](#1-prerequisites)
2. [Install](#2-install)
3. [Get your API keys](#3-get-your-api-keys)
4. [Add the keys to `.env`](#4-add-the-keys-to-env)
5. [Verify the keys](#5-verify-the-keys)
6. [Start the app](#6-start-the-app)
7. [Test it](#7-test-it)
8. [Troubleshooting](#8-troubleshooting)
9. [Configuration reference](#9-configuration-reference)
10. [Project layout](#10-project-layout)
11. [What this shows / what it doesn't](#11-what-this-shows--what-it-doesnt)

---

## 1. Prerequisites

- **Python 3.11 or newer**. Check with `python3 --version`.
- An **OpenAI API account**, a **TypeSafe account**, or both. Either is optional (see MOCK mode above).

## 2. Install

From the project folder:

```bash
python3 -m venv .venv
```

```bash
source .venv/bin/activate
```

On Windows (PowerShell), use `.venv\Scripts\Activate.ps1` instead.

```bash
pip install -r requirements.txt
```

This installs FastAPI, Uvicorn, `openai>=3.26.0` (the minimum version with `client.decisions`, per OpenAI's Decisions guide), `typesafe-sdk`, and pytest.

## 3. Get your API keys

### OpenAI

1. Sign in at **https://platform.openai.com**.
2. Open **API keys** (https://platform.openai.com/api-keys) and click **Create new secret key**.
3. Copy the key. It starts with `sk-` and is shown only once.
4. Make sure the account has billing set up and access to the Decisions API (`gpt-6-luna`). Decisions is in public beta, per the [Decisions guide](https://developers.openai.com/api/docs/guides/decisions).

### TypeSafe

1. Sign in at the TypeSafe console, **https://console.typesafe.ai**. Jev is in early access, so you may need to request access from [typesafe.ai](https://typesafe.ai) first.
2. Create an API key from the dashboard and copy it.
3. Docs: [quickstart](https://docs.typesafe.ai/introduction/quickstart) and [API reference](https://docs.typesafe.ai/api).

> Treat both keys like passwords. `.env` is already listed in `.gitignore`, so don't commit it or paste keys into screenshots.

## 4. Add the keys to `.env`

Copy the template:

```bash
cp .env.example .env
```

Open `.env` and fill in one or both keys:

```dotenv
OPENAI_API_KEY=sk-...your-openai-key...
TYPESAFE_API_KEY=...your-typesafe-key...
```

Leave a key empty to keep that provider in MOCK mode. The app reads `.env` at startup. A variable already exported in your shell takes precedence over the file.

## 5. Verify the keys

```bash
python check_keys.py
```

This makes **one tiny live call per provider**: a single yes/no question about "Hello there!", costing a fraction of a cent. Expected output:

```
Checking API keys...
  openai    OK     model=gpt-6-luna  P(greeting)=0.97  412 ms
  typesafe  OK     model=jev-1.13.0  P(greeting)=0.98  140 ms
```

(Your probabilities, model versions and latencies will differ.)

| You see | Meaning |
|---|---|
| `OK` | The key works and the API answered |
| `MOCK` | No key found for that provider. Check `.env` |
| `FAIL ... 401` | Invalid or revoked key |
| `FAIL ... 403` / `404` | The key works but has no access to the model or endpoint. Check beta or early access |
| `FAIL ... 429` / `529` | Rate-limited or overloaded. Wait and retry |

The script exits with a non-zero code if any live check fails, so you can use it in CI.

## 6. Start the app

```bash
uvicorn server:app --port 8000
```

Open **http://localhost:8000**:

- **`/`** is the overview: what is being compared, how a run works, and the two projects.
- **`/tickets/`** is Project 1, the Support Ticket Router.
- **`/alerts/`** is Project 2, the Cloud Alert Triage.

The pills in the top bar show **LIVE** or **MOCK** for each provider. If you added keys and still see MOCK, restart the server, because `.env` is read only at startup.

Stop the server with **Ctrl+C**. Every call is logged to `decisions_log.sqlite` in the project folder.

## 7. Test it

### a) Unit tests (no keys needed, nothing leaves your machine)

```bash
pytest -q
```

The tests always force MOCK mode, even if keys are set. They cover:
- request building for both vendor formats;
- normalizing each vendor's documented response shape;
- mock determinism;
- ticket and alert routing rules;
- the "why do they differ?" explanation;
- SQLite logging.

### b) Try it in the browser

1. Open http://localhost:8000 and click **Open Ticket Router**.
2. **① Choose a ticket** from the picker. The human label is shown underneath.
3. **② Set your routing rules**. Start with the defaults.
4. **③ Run OpenAI + TypeSafe.**
5. **④ Compare:**
   - **Side by side** shows each answer per provider, with agreement.
   - **Why do they differ?** shows which answer flipped your code's decision, where the probabilities split, and whether each model's recommendation matches what your code derived.
   - **Per-provider detail** shows probability bars, a plain-English reading of each answer, latency, tokens, cost, and the exact request and raw response.
6. Change a threshold and run again to watch the routing decision change.
7. Repeat on **② Alert Triage**. Try A02 (a staging spike), A03 (a slow burn in prod) and A07 (latency doubling after a deploy).

### c) Smoke-test the API from the command line

```bash
curl -s -X POST localhost:8000/tickets/run -H 'content-type: application/json' -d '{"input":"I was charged twice this month","params":{}}'
```

### d) Run the evaluation on all labeled samples

```bash
python eval.py --app tickets
```

```bash
python eval.py --app alerts
```

Each eval prints:
- accuracy against the human labels;
- the agreement rate between providers;
- p50 and p95 latency;
- total cost;
- a calibration table (accuracy per confidence bucket: <0.5 / 0.5–0.7 / 0.7–0.9 / 0.9–1.0).

The tickets eval also runs a **threshold sweep** (0.60–0.95), showing how many tickets go to human review versus how many are misrouted.

With live keys, one full eval run makes 35 small calls per provider (20 tickets + 15 alerts). At list prices that costs well under one cent. Add `--mock` to force MOCK mode even when keys are set.

## 8. Troubleshooting

| Problem | Fix |
|---|---|
| `address already in use` on port 8000 | Another server is running. Stop it with Ctrl+C in its terminal, or use another port: `uvicorn server:app --port 8010` |
| Top bar still says MOCK after adding keys | Restart the server. Check that the key names in `.env` are exactly `OPENAI_API_KEY` and `TYPESAFE_API_KEY` |
| `AttributeError: ... has no attribute 'decisions'` | Your `openai` package is too old. Run `pip install -U "openai>=3.26.0"` |
| `ModuleNotFoundError: typesafe_sdk` | Run `pip install -r requirements.txt` inside the activated venv |
| `401` in the UI or `check_keys.py` | The key is wrong or revoked. Create a new one |
| `422` from TypeSafe | The request failed validation. The error body names the field |
| A provider column shows a red error but the other works | Expected: each provider fails independently and the app keeps running |
| Results look random | You are in MOCK mode. That is by design |

## 9. Configuration reference

All settings are optional and go in `.env`:

| Variable | Default | Used by |
|---|---|---|
| `OPENAI_API_KEY` | – | OpenAI provider (MOCK if empty) |
| `TYPESAFE_API_KEY` | – | TypeSafe provider (MOCK if empty) |
| `TICKETS_CHOICE_THRESHOLD` | `0.75` | Tickets: send to human review below this team confidence |
| `TICKETS_SECURITY_THRESHOLD` | `0.5` | Tickets: send to the security queue above this P(security_sensitive) |
| `ALERTS_PAGE_SEVERITY` | `1.6` | Alerts: page on-call at or above this expected severity |
| `ALERTS_WATCH_SEVERITY` | `0.7` | Alerts: add to the watchlist at or above this |
| `ALERTS_ROLLBACK_DEPLOY_P` | `0.7` | Alerts: roll back if page-level, a recent deploy, and P(deploy cause) ≥ this |
| `DECISIONS_DB` | `decisions_log.sqlite` | Call log location |

The thresholds can also be changed per run in the UI.

## 10. Project layout

```
server.py        one web server: overview at /, projects at /tickets/ and /alerts/
check_keys.py    one tiny live call per provider to verify keys
eval.py          accuracy, agreement, latency, cost, calibration, threshold sweep
common/
  schemas.py     normalized Question / Answer / ProviderResult
  providers.py   DecisionProvider interface, OpenAIProvider, TypeSafeProvider, MOCK mode
  runner.py      runs both providers in parallel, logs every call
  calllog.py     SQLite log (input hash, provider, answers, latency, cost)
  explain.py     "why do they differ?" (counterfactual swaps, splits, consistency)
  web.py         FastAPI factory shared by both projects
  home.html, static/   overview page and shared UI (no build step)
tickets/         Project 1: questions, routing rules, page
alerts/          Project 2: questions, routing rules, page
samples/         tickets.json (20 labeled), alerts.json (15 labeled)
tests/           pytest suite (always MOCK)
```

**How the two APIs map onto one interface:**

| | OpenAI Decisions | TypeSafe Jev |
|---|---|---|
| Yes/no | `predicate` → `probability` | `noul` → `noul` |
| Pick one | `choice` with `choices:[{value, description}]` | `choice` with `criteria:{label: description}` |
| Ordered rating | `score` with `levels:[{label, description}]` | `score` with `criteria:[...]` (2–10 levels) |
| Input | text (JSON is sent as text) | `state`: text or a JSON object |
| List price | $0.10 / 1M input tokens | $0.042 / 1M input tokens |

Both return a distribution plus `confidence` for choice and score, and neither returns a confidence for yes/no. In both, `score` is probability-weighted (Σ level × P(level)), so `1.1` is not a category. Neither API returns a rationale, so the "why" panel is reconstructed from the probabilities and your routing code.

## 11. What this shows / what it doesn't

**Shows**
- Two decision APIs that model the same three question shapes, with small differences in their wire formats that a thin adapter normalizes.
- The architecture pattern: the model answers narrow, typed questions, and **plain code owns the decision**, using thresholds you can test, tune and audit.
- How to evaluate before you trust a model: labels, agreement, calibration buckets, and a threshold sweep that shows the tradeoff between human-review load and misroutes.

**Doesn't show**
- **Which vendor is better.** Twenty tickets and fifteen alerts are a smoke test, not a benchmark. MOCK numbers are random noise.
- **Vendor latency and calibration claims.** These must be validated on *your* data, from *your* region, with *your* prompts. Measured latency here includes network and SDK overhead.
- **That confidence means correctness.** Confidence describes how concentrated the distribution is. **A confident answer can still be wrong.** The calibration table exists so you can check rather than assume.
- **Exact costs.** Costs are list price × input tokens: as reported by the API in live mode, and estimated at about 4 characters per token in MOCK mode (marked "est.").

This is demo code for discussion, not production code: there are no retries beyond the SDK defaults, no auth on the web endpoints, and no PII handling.
