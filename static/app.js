// LedgerMind front end: vendors, invoice, verdict, and the Hindsight memory panel.
const $ = (s) => document.querySelector(s);
const inr = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 });
const money = (x) => inr.format(x || 0);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmtDate = (d) => d ? new Date(d + "T00:00:00").toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" }) : "";
const shortDate = (d) => fmtDate(d).replace(/ \d{4}$/, "");
const initials = (s) => s.split(/\s+/).slice(0, 2).map((w) => w[0]).join("").toUpperCase();
const VERDICT = { approve: "Approve", review: "Review", hold: "Hold" };
const STATUS = { approve: "approved", hold: "held", reject: "rejected" };

// Small inline icon set (stroke icons, 24px grid) so there are no icon-font dependencies.
const ICON = {
  memory: `<svg viewBox="0 0 24 24"><path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/><path d="M12 7v5l4 2"/></svg>`,
  scan: `<svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/><path d="M11 8v6M8 11h6"/></svg>`,
  check: `<svg viewBox="0 0 24 24"><path d="M20 6 9 17l-5-5"/></svg>`,
  save: `<svg viewBox="0 0 24 24"><path d="M12 3v12"/><path d="m7 10 5 5 5-5"/><path d="M5 21h14"/></svg>`,
  file: `<svg viewBox="0 0 24 24"><path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><path d="M14 3v6h6"/></svg>`,
};

const S = { vendors: [], invoices: [], notes: {}, postings: [], reviews: {}, retained: {}, current: null, busy: false };

async function api(path, opts = {}) {
  const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  const data = await res.json().catch(() => ({ error: `HTTP ${res.status}` }));
  if (!res.ok || data.error) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

const inv = (key) => S.invoices.find((i) => i.key === key);
const vendorOf = (i) => S.vendors.find((v) => v.slug === i.vendor);
const posting = (key) => S.postings.find((p) => p.invoice_key === key);
const vendorList = (i) => S.invoices.filter((x) => x.vendor === i.vendor);

// ── Load ──────────────────────────────────────────────────────────────────
async function load() {
  const st = await api("/api/state");
  Object.assign(S, { vendors: st.vendors, invoices: st.invoices, notes: st.notes, postings: st.postings, reviews: st.reviews });
  st.postings.forEach((p) => { if (p.retained && !S.retained[p.invoice_key]) S.retained[p.invoice_key] = { content: p.retained }; });
  $("#bank-id").textContent = st.bank;
  $("#model").textContent = st.model;
  $("#buyer").innerHTML = `Books of <b>${esc(st.buyer.name)}</b>`;
  renderTally();
  const next = S.invoices.find((i) => !posting(i.key)) || S.invoices[0];
  select(next.key);
}

function renderBook() {
  const currentVendor = S.current && inv(S.current).vendor;
  $("#vendors").innerHTML = S.vendors.map((v) => {
    const steps = S.invoices.filter((i) => i.vendor === v.slug).map((i, n) => {
      const p = posting(i.key);
      return `<button class="step ${S.current === i.key ? "is-active" : ""}" data-key="${i.key}" data-status="${p ? p.decision : ""}" type="button"
          aria-label="Invoice ${n + 1} from ${esc(v.short)}${p ? `, ${STATUS[p.decision]}` : ""}">
        <span class="step-node">${p ? (p.decision === "approve" ? "✓" : "!") : n + 1}</span>
        <span class="step-label">${p ? STATUS[p.decision] : shortDate(i.date)}</span></button>`;
    }).join("");
    return `<li class="vendor ${v.slug === currentVendor ? "is-selected" : ""}">
      <div class="vendor-top"><span class="avatar">${initials(v.short)}</span>
        <div><h3>${esc(v.short)}</h3><p class="vendor-cat">${esc(v.category)}</p></div></div>
      ${v.headline ? `<span class="badge badge-memory">Start here · main demo</span>` : ""}
      <div class="stepper">${steps}</div></li>`;
  }).join("");
}

// Count numbers up in the header so changes are noticed during a demo.
function countTo(el, value, fmt) {
  const from = Number(el.dataset.v || 0);
  el.dataset.v = value;
  if (from === value) { el.textContent = fmt(value); return; }
  const t0 = performance.now(), dur = 700;
  const step = (t) => {
    const k = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - k, 3);
    el.textContent = fmt(from + (value - from) * e);
    if (k < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
  el.classList.remove("bump"); void el.offsetWidth; el.classList.add("bump");
}

function renderTally() {
  const flags = S.postings.reduce((n, p) => n + (S.reviews[p.invoice_key]?.with_memory.flags.length ?? (p.verdict === "approve" ? 0 : 1)), 0);
  const saved = S.postings.filter((p) => p.decision !== "approve").reduce((s, p) => s + (p.at_risk || 0), 0);
  countTo($("#t-posted"), S.postings.length, (x) => Math.round(x));
  countTo($("#t-flags"), flags, (x) => Math.round(x));
  countTo($("#t-saved"), saved, (x) => money(Math.round(x)).replace(/\.00$/, ""));
}

// ── Select an invoice ─────────────────────────────────────────────────────
function select(key) {
  if (S.busy) return;
  S.current = key;
  const i = inv(key), v = vendorOf(i);
  renderBook();
  renderSheet(i, S.reviews[key]);
  $("#memory-vendor").textContent = v.name;
  $("#ask-vendor").textContent = v.short;
  $("#ask-chips").innerHTML = [`What should I check before paying ${v.short}?`, "Have they ever been disputed?", "Usual rates and terms?"]
    .map((q) => `<button type="button" class="chip">${esc(q)}</button>`).join("");
  $("#answer").hidden = true;
  const review = S.reviews[key];
  if (review) { renderVerdict(i, review); renderThread(i, review); }
  else { $("#verdict").hidden = true; $("#post").hidden = true; showKnown(i); }
  renderPosted(i);
  renderCoach(i);
}

// ── Coach + flow: tells a first-time viewer where they are and what to do next ──
function renderCoach(i) {
  const v = vendorOf(i);
  const list = vendorList(i);
  const n = list.indexOf(i) + 1;
  const p = posting(i.key), review = S.reviews[i.key];
  const phase = p ? 3 : review ? 2 : 1;
  const next = list.find((x) => !posting(x.key) && x.key !== i.key);
  const nextNo = next ? list.indexOf(next) + 1 : 0;

  document.querySelectorAll("#flow li").forEach((li) => {
    const s = Number(li.dataset.step);
    li.classList.toggle("is-active", s === phase);
    li.classList.toggle("is-done", s < phase || (phase === 3 && s === 3));
  });

  const text = {
    1: n === 1
      ? `<b>Invoice ${n} of ${list.length}.</b> ${esc(v.short)} is new, so memory is empty. Click <b>Examine with memory</b> to set the baseline.`
      : `<b>Invoice ${n} of ${list.length}.</b> Watch the Memory panel: LedgerMind will recall what it learned from ${n > 2 ? "earlier invoices" : "invoice 1"} before judging this one.`,
    2: `<b>Verdict ready${review?.memories.length ? `, using ${review.memories.length} memories` : ""}.</b> Check the flags, then post your decision. It gets saved to memory.`,
    3: next ? `<b>Saved to memory.</b> Now open invoice ${nextNo} and see if LedgerMind catches anything with what it just learned.`
            : `<b>All of ${esc(v.short)}'s invoices are done.</b> Ask memory a question on the right, or pick another vendor.`,
  }[phase];
  const btn = phase === 2 ? `<button class="btn btn-sm" type="button" data-coach="decide">Go to decision</button>`
    : phase === 3 && next ? `<button class="btn btn-primary btn-sm" type="button" data-coach="next">Open invoice ${nextNo}</button>` : "";
  const guide = $("#guide");
  guide.className = `coach ${phase === 3 ? "is-memory" : ""}`;
  guide.innerHTML = `<span class="coach-icon">${phase}</span><p>${text}</p>${btn}`;
  const b = guide.querySelector("[data-coach]");
  if (b) b.onclick = () => (b.dataset.coach === "decide" ? $("#post").scrollIntoView({ behavior: "smooth", block: "center" }) : select(next.key));
}

function renderSheet(i, review) {
  const v = vendorOf(i);
  const flags = review?.with_memory.flags || [];
  const lineFlag = {};
  flags.forEach((f, n) => { if (Number.isInteger(f.line_index)) lineFlag[f.line_index] = n + 1; });
  const termsFlagged = flags.some((f) => f.kind === "terms_change");
  const n = vendorList(i).indexOf(i) + 1;
  const rows = i.lines.map((l, k) => `
    <tr class="${lineFlag[k] ? "is-flagged" : ""}">
      <td>${lineFlag[k] ? `<span class="flag-pin" title="Flag ${lineFlag[k]}">${lineFlag[k]}</span>` : ""}${esc(l.description)}</td>
      <td class="r hide-sm">${l.qty.toLocaleString("en-IN")} ${esc(l.unit)}</td>
      <td class="r hide-sm">${money(l.rate)}</td>
      <td class="r">${money(l.amount)}</td>
    </tr>`).join("");
  const cols = matchMedia("(max-width: 860px)").matches ? 1 : 3; // qty/rate are hidden on phones
  $("#sheet").innerHTML = `
    <div class="invoice-head">
      <div>
        <span class="badge badge-primary">Invoice ${n} of ${vendorList(i).length}</span>
        <h2>${esc(v.name)}</h2>
        <p class="invoice-from">${esc(v.city)} · GSTIN ${esc(v.gstin)}</p>
      </div>
      <div class="invoice-cta">
        <button class="btn btn-primary btn-lg" id="examine" type="button">${ICON.scan}${review ? "Examine again" : "Examine with memory"}</button>
        <small>${review ? "Re-runs recall and review" : "Recalls vendor history, then reviews"}</small>
      </div>
    </div>
    <dl class="meta">
      <div><dt>Invoice no.</dt><dd>${esc(i.number)}</dd></div>
      <div><dt>Dated</dt><dd>${fmtDate(i.date)}</dd></div>
      <div><dt>PO</dt><dd>${esc(i.po)}</dd></div>
      <div class="${termsFlagged ? "is-flagged" : ""}"><dt>Payment terms</dt><dd>Net ${i.terms_days}</dd></div>
    </dl>
    <div class="table-wrap">
      <table class="lines">
        <thead><tr><th>Particulars</th><th class="r hide-sm">Qty</th><th class="r hide-sm">Rate</th><th class="r">Amount</th></tr></thead>
        <tbody>${rows}</tbody>
        <tfoot>
          <tr><td class="label" colspan="${cols}">Subtotal</td><td class="r">${money(i.subtotal)}</td></tr>
          <tr><td class="label" colspan="${cols}">GST 18%</td><td class="r">${money(i.tax)}</td></tr>
          <tr class="total"><td class="label" colspan="${cols}">Invoice total</td><td class="r">${money(i.total)}</td></tr>
        </tfoot>
      </table>
    </div>
    <div class="invoice-foot"><p><b>Scenario:</b> ${esc(i.story)}</p></div>
    <ol class="steps" id="steps" hidden></ol>`;
  $("#examine").onclick = () => examine(i.key);
}

// ── Before any review: show what's already remembered about the vendor ──
async function showKnown(i) {
  const v = vendorOf(i);
  $("#thread-sub").innerHTML = `Everything remembered about ${esc(v.short)} so far`;
  $("#timeline").innerHTML = skeleton(3);
  try {
    const { memories } = await api(`/api/vendor/${v.slug}/memory`);
    if (S.current !== i.key) return;
    $("#timeline").innerHTML = memories.length
      ? memories.map((m, k) => memItem(m, false, [], [], k)).join("")
      : `<li class="empty"><div class="mem"><p class="empty-text"><b>Memory is empty for ${esc(v.short)}.</b>
         Everything LedgerMind learns about them starts with the decision you post.</p></div></li>`;
  } catch (e) {
    $("#timeline").innerHTML = `<li class="empty"><p class="error">${esc(e.message)}</p></li>`;
  }
}

const skeleton = (n) => Array.from({ length: n }, (_, k) => `<li class="empty" style="--i:${k}"><div class="skeleton"></div></li>`).join("");

function memItem(m, withRefs, cites = [], records = [], k = 0) {
  const rec = records.find((r) => r.ref === m.record);
  return `<li class="${cites.length ? "is-cited" : ""}" data-ref="${m.ref || ""}" style="--i:${k}">
    <div class="mem">
      <div class="mem-date">${withRefs ? `<span class="mem-ref">${m.ref}</span>` : ""}${fmtDate(m.date)}</div>
      <p class="mem-text">${esc(m.text)}</p>
      <div class="mem-meta">
        <span class="kind ${m.type}">${m.type === "observation" ? "learned pattern" : m.type === "experience" ? "experience" : "fact"}</span>
        ${withRefs ? `<span title="Relevance ${m.score}"><span class="relevance"><i style="width:${Math.min(100, Math.round(m.score * 100))}%"></i></span></span>
        <span>${m.source === "both" ? "both queries" : m.source === "similar" ? "similar-issue search" : "vendor profile"}</span>` : ""}
        ${cites.length ? `<span class="cited">cited by flag ${cites.join(", ")}</span>` : ""}
      </div>
      ${rec ? `<details class="record"><summary>Source record ${rec.ref}</summary><p>${esc(rec.text)}</p></details>` : ""}
    </div>
  </li>`;
}

// ── Examine: recall → review (with + without memory) ─────────────────────
async function examine(key) {
  if (S.busy) return;
  S.busy = true;
  const i = inv(key), v = vendorOf(i);
  $("#examine").disabled = true;
  $("#verdict").hidden = true; $("#post").hidden = true; $("#posted").hidden = true;
  $(".memory-icon").classList.add("is-busy");
  $("#timeline").innerHTML = skeleton(4);
  $("#thread-sub").textContent = `Recalling ${v.short} from Hindsight…`;
  const steps = $("#steps");
  steps.hidden = false;
  const labels = [`Recalling ${v.short}'s billing history from Hindsight`, "Searching memory for past issues like these lines",
    "Reviewing with memory, and again without it"];
  steps.innerHTML = labels.map((l) => `<li>${l}</li>`).join("");
  const lis = [...steps.children];
  let n = 0;
  lis[0].classList.add("is-on");
  const tick = setInterval(() => {
    if (n < lis.length - 1) { lis[n].classList.replace("is-on", "is-done"); lis[++n].classList.add("is-on"); }
  }, 900);
  const done = () => { clearInterval(tick); S.busy = false; $(".memory-icon").classList.remove("is-busy"); };
  try {
    const review = await api(`/api/analyze/${key}`, { method: "POST" });
    S.reviews[key] = review;
    done();
    if (S.current !== key) return;
    renderSheet(i, review);
    renderVerdict(i, review);
    renderThread(i, review);
    renderCoach(i);
    $("#verdict").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (e) {
    done();
    steps.insertAdjacentHTML("afterend", `<p class="error">${esc(e.message)}</p>`);
    $("#examine").disabled = false;
    showKnown(i);
  }
}

function citeMap(review) {
  const map = {};
  review.with_memory.flags.forEach((f, n) => (f.memory_refs || []).forEach((r) => (map[r] ||= []).push(n + 1)));
  return map;
}

const refPill = (r) => `<span class="mem-ref" data-ref="${r}" title="Show memory ${r}">${r}</span>`;
const markRefs = (text) => esc(text).replace(/\[(M\d+)\]/g, (_, r) => refPill(r));

function renderVerdict(i, review) {
  const w = review.with_memory, s = review.stateless;
  const noMemory = review.memories.length === 0;
  const differs = w.verdict !== s.verdict;
  const flags = w.flags.map((f, n) => `
    <li class="flag" data-refs="${(f.memory_refs || []).join(" ")}">
      <span class="no">${n + 1}</span>
      <div><h3>${esc(f.title)}<span class="sev ${f.severity}">${f.severity}</span>${f.recurring ? `<span class="sev recurring">recurring</span>` : ""}</h3>
        <p>${markRefs(f.detail)} ${(f.memory_refs || []).map(refPill).join(" ")}</p></div>
      <span class="amt">${f.amount_at_risk ? money(f.amount_at_risk) : ""}</span>
    </li>`).join("");
  const box = $("#verdict");
  box.dataset.verdict = w.verdict;
  box.innerHTML = `
    <div class="verdict-head">
      <div class="stamp ${w.verdict}">${VERDICT[w.verdict].toUpperCase()}</div>
      <div>
        <h2>${esc(w.headline)}</h2>
        <p class="action">${esc(w.recommended_action || "")}</p>
      </div>
    </div>
    <div class="compare">
      <div class="compare-col"><h4>Without memory</h4><div class="v ${s.verdict}">${VERDICT[s.verdict]}</div><p>${esc(s.headline)}</p></div>
      <div class="compare-vs">vs</div>
      <div class="compare-col with"><h4>${ICON.memory}With ${review.memories.length} ${review.memories.length === 1 ? "memory" : "memories"}</h4>
        <div class="v ${w.verdict}">${VERDICT[w.verdict]}${w.amount_at_risk ? ` · ${money(w.amount_at_risk)}` : ""}</div>
        <p>${w.flags.length} flag${w.flags.length === 1 ? "" : "s"} raised${w.amount_at_risk ? " · amount at risk" : ""}</p></div>
      <p class="compare-note">${noMemory ? "First invoice from this vendor: nothing to remember yet, so both agents agree."
        : differs ? "Same invoice, same model. The only difference is memory." : "Memory confirms this matches the vendor's history."}</p>
    </div>
    ${flags ? `<ol class="flags">${flags}</ol>` : ""}
    <details class="reasoning" open><summary>Why LedgerMind decided this</summary><p>${markRefs(w.reasoning)}</p></details>`;
  box.hidden = false;
  bindHighlights();
  const p = posting(i.key);
  $("#post").hidden = !!p;
  if (!p) $("#note").value = S.notes[i.key] || "";
}

function renderThread(i, review) {
  const v = vendorOf(i);
  const cites = citeMap(review);
  const q = review.queries;
  const ms = review.timings_ms;
  let html = `<li class="q" style="--i:0"><div class="mem">
      <div class="mem-date">recall() · ${Math.max(ms.profile, ms.similar)} ms</div>
      <p class="q-title">Asked Hindsight two questions about ${esc(v.short)}</p>
      <ul class="q-list"><li>${esc(q.profile)}</li><li>${esc(q.similar.slice(0, 120))}${q.similar.length > 120 ? "…" : ""}</li></ul>
    </div></li>`;
  html += review.memories.length
    ? review.memories.map((m, k) => memItem(m, true, cites[m.ref] || [], review.records, k + 1)).join("")
    : `<li class="empty" style="--i:1"><div class="mem"><p class="empty-text"><b>Nothing came back.</b> LedgerMind has never seen ${esc(v.short)}, so this invoice sets the baseline.</p></div></li>`;
  const r = S.retained[i.key];
  if (r) html += retainedItem(r, review.memories.length + 2);
  $("#timeline").innerHTML = html;
  $("#thread-sub").innerHTML = `${review.memories.length} memories recalled for <b>${esc(i.number)}</b> · bank <code>${esc(review.bank)}</code>`;
  bindHighlights();
}

function retainedItem(r, k = 0) {
  return `<li class="w" style="--i:${k}"><div class="mem">
    <div class="mem-date">retain()${r.ms ? ` · ${r.ms} ms` : ""}</div>
    <p class="q-title">Written back to memory</p>
    <p class="mem-text">The invoice, its flags and your note are stored, so the next invoice is judged against them.</p>
    <details><summary>Show exactly what was stored</summary><pre>${esc(r.content)}</pre></details>
  </div></li>`;
}

// hovering a flag or an M# pill lights up the memory it relied on
function bindHighlights() {
  document.querySelectorAll(".mem-ref[data-ref], .flag[data-refs]").forEach((el) => {
    if (el.closest("#timeline")) return;
    const refs = el.dataset.ref ? [el.dataset.ref] : el.dataset.refs.split(" ").filter(Boolean);
    const lit = (on) => refs.forEach((r) => document.querySelector(`#timeline li[data-ref="${r}"]`)?.classList.toggle("is-lit", on));
    el.onmouseenter = () => lit(true);
    el.onmouseleave = () => lit(false);
    el.onclick = (e) => {
      e.stopPropagation();
      document.querySelector(`#timeline li[data-ref="${refs[0]}"]`)?.scrollIntoView({ behavior: "smooth", block: "center" });
    };
  });
}

// ── Post a decision → retain() ────────────────────────────────────────────
async function commit(decision) {
  const key = S.current;
  const buttons = document.querySelectorAll(".post-actions .btn");
  buttons.forEach((b) => (b.disabled = true));
  $("#post").querySelector(".error")?.remove();
  $(".memory-icon").classList.add("is-busy");
  try {
    const res = await api(`/api/commit/${key}`, { method: "POST", body: JSON.stringify({ decision, note: $("#note").value }) });
    S.postings = res.postings;
    S.retained[key] = res.retained;
    $("#post").hidden = true;
    renderBook(); renderTally();
    renderThread(inv(key), S.reviews[key]);
    renderPosted(inv(key));
    renderCoach(inv(key));
    $("#timeline li.w")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  } catch (e) {
    $("#post").insertAdjacentHTML("beforeend", `<p class="error">${esc(e.message)}</p>`);
  } finally {
    buttons.forEach((b) => (b.disabled = false));
    $(".memory-icon").classList.remove("is-busy");
  }
}

function renderPosted(i) {
  const p = posting(i.key);
  const box = $("#posted");
  if (!p) { box.hidden = true; return; }
  const list = vendorList(i);
  const next = list.find((x) => !posting(x.key));
  const disputed = p.decision !== "approve" && S.reviews[i.key];
  box.innerHTML = `
    <h3>${ICON.check}Posted as ${STATUS[p.decision]} and saved to memory</h3>
    <p>The next invoice from ${esc(vendorOf(i).short)} will be checked against this one.</p>
    <div class="row">
      ${next ? `<button class="btn btn-primary" type="button" data-go="${next.key}">Open invoice ${list.indexOf(next) + 1} · ${esc(next.number)}</button>` : ""}
      ${disputed ? `<a class="btn" href="/api/dispute/${i.key}.pdf" target="_blank" rel="noopener">${ICON.file}Dispute notice PDF</a>` : ""}
    </div>`;
  box.hidden = false;
  box.querySelector("[data-go]")?.addEventListener("click", (e) => select(e.currentTarget.dataset.go));
}

// ── Ask memory (reflect) ──────────────────────────────────────────────────
async function ask(question) {
  const box = $("#answer");
  const v = vendorOf(inv(S.current));
  box.hidden = false;
  box.innerHTML = `<div class="skeleton"></div>`;
  try {
    const r = await api("/api/ask", { method: "POST", body: JSON.stringify({ vendor: v.slug, question }) });
    const html = window.marked ? DOMPurify.sanitize(marked.parse(r.answer)) : esc(r.answer);
    box.innerHTML = html + (r.based_on.length ? `<p class="basis">Based on ${r.based_on.length} memories · Hindsight reflect()</p>` : "");
  } catch (e) {
    box.innerHTML = `<p class="error">${esc(e.message)}</p>`;
  }
}

// ── Wiring ────────────────────────────────────────────────────────────────
$("#vendors").addEventListener("click", (e) => { const t = e.target.closest(".step"); if (t) select(t.dataset.key); });
document.querySelectorAll(".post-actions .btn").forEach((b) => b.addEventListener("click", () => commit(b.dataset.decision)));
$("#ask").addEventListener("submit", (e) => { e.preventDefault(); const q = $("#ask-q").value.trim(); if (q) ask(q); });
$("#ask-chips").addEventListener("click", (e) => { const c = e.target.closest(".chip"); if (c) { $("#ask-q").value = c.textContent; ask(c.textContent); } });
$("#reset-btn").addEventListener("click", async () => {
  if (!confirm("Wipe this workspace's memory bank and start the demo over?")) return;
  await api("/api/reset", { method: "POST" });
  Object.assign(S, { reviews: {}, retained: {}, current: null });
  load();
});

load().catch((e) => { $("#sheet").innerHTML = `<p class="error">Could not load LedgerMind: ${esc(e.message)}</p>`; });
