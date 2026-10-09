// Shared rendering for both apps: the problem definition, a comparison table,
// and two provider columns with probability bars, readings, and raw payloads.
const LABELS = { openai: "OpenAI · gpt-6-luna", typesafe: "TypeSafe · Jev" };
const KIND_HELP = {
  predicate: "Yes/no. Returns one probability that the statement is true. No confidence is returned.",
  choice: "Pick one of N unordered options. Returns a distribution over options plus a confidence.",
  score: "Rate on ordered levels. Returns a distribution over levels; the score is Σ level × P(level), " +
         "so it can fall between levels.",
};
const VENDOR_KIND = { openai: { predicate: "predicate", choice: "choice", score: "score" },
                      typesafe: { predicate: "noul", choice: "choice", score: "score" } };
const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const pct = p => (p * 100).toFixed(1) + "%";
let QUESTIONS = {};

// ---- shared top bar: brand, the two projects as tabs, and provider mode pills
const PROJECTS = [
  { id: "tickets", n: 1, href: "/tickets/", title: "Ticket Router", sub: "unstructured text" },
  { id: "alerts", n: 2, href: "/alerts/", title: "Alert Triage", sub: "structured JSON" },
];

async function renderShell(active) {
  const tabs = [`<a href="/" class="tab ${active === "home" ? "on" : ""}">Overview</a>`,
    ...PROJECTS.map(p => `<a href="${p.href}" class="tab ${active === p.id ? "on" : ""}">
      <span class="num">${p.n}</span>${p.title}<small>${p.sub}</small></a>`)].join("");
  const bar = document.createElement("header");
  bar.className = "topbar";
  bar.innerHTML = `<div class="topbar-in">
      <a href="/" class="brand"><span class="logo">⇄</span><span>Decision Models <b>Showdown</b></span></a>
      <nav class="tabs">${tabs}</nav>
      <div class="status" id="status"></div></div>`;
  document.body.prepend(bar);
  try {
    const s = await (await fetch("status")).json();
    document.getElementById("status").innerHTML = Object.entries(s).map(([p, m]) =>
      `<span class="pill ${m}" title="${m === "mock" ? "No API key: deterministic fake probabilities" : "Calling the real API"}">
        ${LABELS[p].split(" · ")[0]} <b>${m.toUpperCase()}</b></span>`).join("");
  } catch { /* status is decorative */ }
}

async function loadSamples(select, onPick) {
  const samples = await (await fetch("samples")).json();
  select.innerHTML = samples.map((s, i) => `<option value="${i}">${esc(s.id)} — ${esc(s.note || s.text.slice(0, 60))}</option>`).join("");
  select.onchange = () => onPick(samples[select.value]);
  onPick(samples[0]);
}

// ---- the problem: what each question asks and what its options mean
async function loadQuestions(container) {
  const qs = await (await fetch("questions")).json();
  QUESTIONS = Object.fromEntries(qs.map(q => [q.name, q]));
  container.innerHTML = `<details class="problem"><summary>What both models are asked: ${qs.length} questions in one request
    <span class="chips">${qs.map(q => `<span class="chip">${esc(q.name)} <i>${q.kind}</i></span>`).join("")}</span></summary>
    <div class="qgrid">${qs.map(q => `<div class="qdef">
      <div class="qdef-head"><b>${esc(q.name)}</b><span class="kind">${q.kind}</span></div>
      <p>${esc(q.instructions)}</p>
      ${q.options.length ? `<ol ${q.kind === "score" ? 'start="0"' : 'class="plain"'}>${q.options.map(o =>
        `<li><code>${esc(o.value)}</code> ${esc(o.description)}</li>`).join("")}</ol>` : ""}
      <p class="help">${KIND_HELP[q.kind]} Sent as <code>${VENDOR_KIND.openai[q.kind]}</code> to OpenAI and
        <code>${VENDOR_KIND.typesafe[q.kind]}</code> to TypeSafe.</p></div>`).join("")}</div></details>`;
}

const optDesc = (q, v) => (QUESTIONS[q]?.options.find(o => o.value === v) || {}).description || "";
const levelName = (q, i) => (QUESTIONS[q]?.options[i] || {}).value || i;
const sorted = dist => Object.entries(dist).sort((a, b) => b[1] - a[1]);

// ---- plain-English reading of one answer
function reading(a) {
  if (a.kind === "predicate") {
    const p = a.value;
    const verdict = p >= 0.7 ? "likely <b>yes</b>" : p <= 0.3 ? "likely <b>no</b>" : "<b>uncertain</b> (0.3–0.7)";
    return `${verdict}: P(true) = ${p.toFixed(2)}. Your code compares this probability to a threshold.`;
  }
  const [[topK, topP], [secK, secP] = ["–", 0]] = sorted(a.distribution);
  if (a.kind === "choice")
    return `Picks <b>${esc(a.value)}</b> (${esc(optDesc(a.name, a.value))}) at ${pct(topP)}. Runner-up
      <b>${esc(secK)}</b> at ${pct(secP)}, a margin of ${((topP - secP) * 100).toFixed(0)} points.`;
  const near = Math.round(a.value);
  return `Expected value <b>${a.value.toFixed(2)}</b>, nearest level ${near} “${esc(levelName(a.name, near))}”.
    Most likely single level: ${topK} “${esc(levelName(a.name, +topK))}” at ${pct(topP)}.
    ${Math.abs(a.value - near) > 0.25 ? "The value sits between levels: the model is split." : ""}`;
}

function bars(dist, top, name, isScore) {
  return Object.entries(dist).map(([k, p]) => {
    const label = isScore ? `${k} ${levelName(name, +k)}` : k;
    const tip = isScore ? optDesc(name, levelName(name, +k)) : optDesc(name, k);
    return `<div class="bar"><span class="lbl ${k === top ? "top" : ""}" title="${esc(tip || label)}">${esc(label)}</span>
      <span class="track"><span class="fill" style="width:${(p * 100).toFixed(1)}%;display:block"></span></span>
      <span class="pv">${pct(p)}</span></div>`;
  }).join("");
}

function renderAnswer(a) {
  const conf = a.confidence == null ? "no confidence returned" : `confidence ${a.confidence.toFixed(2)}`;
  let body;
  if (a.kind === "predicate") body = bars(a.distribution, a.value >= 0.5 ? "true" : "false", a.name);
  else if (a.kind === "choice") body = bars(a.distribution, a.value, a.name);
  else {
    const n = Object.keys(a.distribution).length - 1, x = (a.value / n) * 100;
    body = bars(a.distribution, sorted(a.distribution)[0][0], a.name, true) +
      `<div class="ev"><i style="left:${x}%"></i><em style="left:${x}%">${a.value.toFixed(2)}</em></div>`;
  }
  const head = a.kind === "choice" ? esc(a.value) : a.kind === "predicate" ? `P(true) = ${a.value.toFixed(2)}`
             : `score ${a.value.toFixed(2)}`;
  return `<div class="q"><div class="q-head"><b>${esc(a.name)}</b><span>${head} · ${conf}</span></div>
    ${body}<p class="reading">${reading(a)}</p></div>`;
}

// ---- side-by-side agreement per question
function compareTable(results) {
  const [a, b] = results;
  const fmt = x => !x ? "—" : x.kind === "choice" ? esc(x.value) + (x.confidence != null ? ` <small>(${x.confidence.toFixed(2)})</small>` : "")
                  : x.value.toFixed(2);
  const agree = (x, y) => {
    if (!x || !y) return ["n/a", ""];
    if (x.kind === "choice") return x.value === y.value ? ["same pick", "ok"] : ["different pick", "bad"];
    if (x.kind === "predicate") {
      const d = Math.abs(x.value - y.value);
      return (x.value >= 0.5) === (y.value >= 0.5) ? [`same side of 0.5 (Δ ${d.toFixed(2)})`, "ok"] : [`opposite (Δ ${d.toFixed(2)})`, "bad"];
    }
    const d = Math.abs(x.value - y.value);
    return d < 0.5 ? [`within 0.5 (Δ ${d.toFixed(2)})`, "ok"] : [`apart by ${d.toFixed(2)}`, "bad"];
  };
  const names = Object.keys(QUESTIONS);
  const rows = names.map(n => {
    const [txt, cls] = agree(a.answers[n], b.answers[n]);
    return `<tr><td><code>${esc(n)}</code></td><td>${fmt(a.answers[n])}</td><td>${fmt(b.answers[n])}</td><td class="${cls}">${txt}</td></tr>`;
  });
  const d1 = a.routing.queue || a.routing.action, d2 = b.routing.queue || b.routing.action;
  rows.push(`<tr class="final"><td>code decision</td><td>${esc(d1)}</td><td>${esc(d2)}</td>
    <td class="${d1 === d2 ? "ok" : "bad"}">${d1 === d2 ? "same outcome" : "different outcome"}</td></tr>`);
  return `<table class="compare"><thead><tr><th>question</th><th>${LABELS[a.provider]}</th><th>${LABELS[b.provider]}</th><th>agreement</th></tr></thead>
    <tbody>${rows.join("")}</tbody></table>`;
}

// ---- why the providers differ (built server-side in common/explain.py)
function whyPanel(x) {
  const L = p => LABELS[p].split(" · ")[0];
  const v = n => typeof n === "number" ? n.toFixed(2) : esc(n);
  const conf = d => d.confidence == null ? "" :
    ` · confidence ${d.confidence.toFixed(2)}${d.low_confidence ? ` <span class="flag">low: the model itself is unsure</span>` : ""}`;

  const mock = x.any_mock ? `<p class="mockwarn"><b>MOCK data.</b> These probabilities are random, so this disagreement
    means nothing about either model. The panel shows how a real disagreement is explained once you add API keys.</p>` : "";

  const decision = x.same_outcome
    ? `<p>Both lead to the same outcome: <b>${esc(Object.values(x.outcomes)[0])}</b>.</p>`
    : x.decisive.length
      ? `<ul>${x.decisive.map(d => `<li>Swap <b>${L(d.from)}'s ${esc(d.question)}</b> (${v(d.value)}) into ${L(d.into)}'s
          result, and your code changes ${L(d.into)}'s outcome from <code>${esc(d.before)}</code> to <code>${esc(d.after)}</code>.
          <b>${esc(d.question)}</b> alone explains the different outcome.</li>`).join("")}</ul>`
      : `<p>No single answer flips the outcome on its own. The difference comes from several answers combined.</p>`;

  const splits = x.disagreements.length ? x.disagreements.map(d => `<div class="split"><code>${esc(d.question)}</code>
      ${Object.keys(x.outcomes).map(p => `<div><b>${L(p)}:</b> ${esc(d[p].text)}${conf(d[p])}</div>`).join("")}</div>`).join("")
    : `<p>The model answers agree on every question.</p>`;

  const cons = x.consistency.length ? `<h5>3. Model recommendation vs. your code</h5><ul>${x.consistency.map(c => c.agrees
      ? `<li><b>${L(c.provider)}</b> recommended <code>${esc(c.model_says)}</code>, and your code's thresholds on its other answers agree.</li>`
      : `<li><b>${L(c.provider)}</b> recommended <code>${esc(c.model_says)}</code>, but your code derived <code>${esc(c.code_says)}</code>
          from its other answers. The model gave that option only ${pct(c.p_code_choice)}. The model's own answers
          disagree with each other, so trust the code path, which uses thresholds you control.</li>`).join("")}</ul>` : "";

  return `<div class="why"><h4>Why do they differ?</h4>${mock}
    <p class="muted">Neither API returns a rationale, only probabilities and confidence. This explanation is
      reconstructed from what can be observed.</p>
    <h5>1. What changed your code's decision</h5>${decision}
    <h5>2. Where the models' probabilities split</h5>${splits}${cons}</div>`;
}

function rawBlock(r) {
  const j = x => esc(JSON.stringify(x, null, 2));
  return `<details class="raw"><summary>Request sent (${r.provider} wire format)</summary><pre>${j(r.request)}</pre></details>
    <details class="raw"><summary>Raw response${r.mode === "mock" ? " (mock, same shape as live)" : ""}</summary><pre>${j(r.raw)}</pre></details>`;
}

function renderResults(container, data, { decisionText }) {
  const cols = data.results.map(r => {
    const d = r.routing;
    const answers = Object.values(r.answers).map(renderAnswer).join("");
    return `<section class="card">
      <h2>${LABELS[r.provider] || r.provider} <span class="badge ${r.mode}">${r.mode.toUpperCase()}</span></h2>
      <div class="meta">model <code>${esc(r.model || "?")}</code> · ${r.latency_ms.toFixed(0)} ms ·
        ${r.input_tokens ?? "?"} input tokens${r.cost_is_estimate ? " (est.)" : ""} · $${r.cost_usd.toFixed(8)}</div>
      ${r.error ? `<p class="error">${esc(r.error)}</p>` : ""}
      <div class="decision ${d.escalated ? "escalated" : ""}"><div>Your code decided: <strong>${esc(decisionText(d))}</strong></div>
        <ul>${d.reasons.map(x => `<li>${esc(x)}</li>`).join("")}</ul></div>
      ${answers}${rawBlock(r)}</section>`;
  }).join("");
  container.innerHTML = `<div class="step-head"><span class="stepnum">4</span><div><h2>Compare the answers</h2>
      <p>Same input, same questions, both providers in parallel. Agreement first, then why they differ, then the full detail.</p></div></div>
    ${compareTable(data.results)}${whyPanel(data.explanation)}
    <h3 class="section">Per-provider detail</h3><div class="cols">${cols}</div>`;
  container.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function runDecision(button, container, input, params, opts) {
  button.disabled = true;
  try {
    const res = await fetch("run", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ input, params }) });
    if (!res.ok) throw new Error(await res.text());
    renderResults(container, await res.json(), opts);
  } catch (e) {
    container.innerHTML = `<p class="error">${esc(e.message)}</p>`;
  } finally { button.disabled = false; }
}
