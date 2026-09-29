// LedgerMind front end: vendor book, invoice folio, and the Hindsight memory thread.
const $ = (s) => document.querySelector(s);
const inr = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 });
const money = (x) => inr.format(x || 0);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmtDate = (d) => d ? new Date(d + "T00:00:00").toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" }) : "";
const VERDICT = { approve: "Approve", review: "Review", hold: "Hold" };
const STATUS = { approve: "approved", hold: "held", reject: "rejected" };

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

// ── Load ──────────────────────────────────────────────────────────────────
async function load() {
  const st = await api("/api/state");
  Object.assign(S, { vendors: st.vendors, invoices: st.invoices, notes: st.notes, postings: st.postings, reviews: st.reviews });
  st.postings.forEach((p) => { if (p.retained && !S.retained[p.invoice_key]) S.retained[p.invoice_key] = { content: p.retained }; });
  $("#bank-id").textContent = st.bank;
  $("#model").textContent = st.model;
  $("#buyer").innerHTML = `Books of <b>${esc(st.buyer.name)}</b>${esc(st.buyer.address)}`;
  renderBook();
  renderTally();
  const next = S.invoices.find((i) => !posting(i.key)) || S.invoices[0];
  select(next.key);
}

function renderBook() {
  $("#vendors").innerHTML = S.vendors.map((v) => {
    const tabs = S.invoices.filter((i) => i.vendor === v.slug).map((i, n) => {
      const p = posting(i.key);
      return `<button class="inv-tab ${S.current === i.key ? "is-active" : ""}" data-key="${i.key}" data-status="${p ? p.decision : ""}" type="button">
        <b>${n + 1}</b><span>${p ? STATUS[p.decision] : fmtDate(i.date).replace(/ \d{4}$/, "")}</span></button>`;
    }).join("");
    return `<li class="vendor ${v.headline ? "is-headline" : ""}"><h3>${esc(v.short)}</h3><p>${esc(v.category)}</p><div class="inv-tabs">${tabs}</div></li>`;
  }).join("");
}

function renderTally() {
  const flags = S.postings.reduce((n, p) => n + (S.reviews[p.invoice_key]?.with_memory.flags.length ?? (p.verdict === "approve" ? 0 : 1)), 0);
  const saved = S.postings.filter((p) => p.decision !== "approve").reduce((s, p) => s + (p.at_risk || 0), 0);
  $("#t-posted").textContent = S.postings.length;
  $("#t-flags").textContent = flags;
  $("#t-saved").textContent = money(saved).replace(/\.00$/, "");
}

// ── Select an invoice ─────────────────────────────────────────────────────
function select(key) {
  if (S.busy) return;
  S.current = key;
  const i = inv(key), v = vendorOf(i);
  renderBook();
  renderSheet(i, S.reviews[key]);
  $("#ask-vendor").textContent = v.short;
  $("#ask-chips").innerHTML = [`What should I check before paying ${v.short}?`, "Have they ever been disputed?", "What are their usual rates and terms?"]
    .map((q) => `<button type="button" class="chip">${esc(q)}</button>`).join("");
  $("#answer").hidden = true;
  $("#guide").hidden = !v.headline || S.postings.length >= 3;
  const review = S.reviews[key];
  if (review) { renderVerdict(i, review); renderThread(i, review); }
  else { $("#verdict").hidden = true; $("#post").hidden = true; showKnown(i); }
  renderPosted(i);
}

function renderSheet(i, review) {
  const v = vendorOf(i);
  const flags = review?.with_memory.flags || [];
  const lineFlag = {};
  flags.forEach((f, n) => { if (Number.isInteger(f.line_index)) lineFlag[f.line_index] = n + 1; });
  const termsFlagged = flags.some((f) => f.kind === "terms_change");
  const rows = i.lines.map((l, n) => `
    <tr class="${lineFlag[n] ? "is-flagged" : ""}">
      <td>${lineFlag[n] ? `<span class="margin-note" title="Flag ${lineFlag[n]}">${lineFlag[n]}</span>` : ""}${esc(l.description)}</td>
      <td class="r hide-sm">${l.qty.toLocaleString("en-IN")} ${esc(l.unit)}</td>
      <td class="r hide-sm">${money(l.rate)}</td>
      <td class="r">${money(l.amount)}</td>
    </tr>`).join("");
  $("#sheet").innerHTML = `
    <div class="sheet-head">
      <div><h1>${esc(v.name)}</h1><p class="from">${esc(v.city)} · GSTIN ${esc(v.gstin)}</p></div>
      <dl class="meta">
        <dt>Invoice</dt><dd>${esc(i.number)}</dd>
        <dt>Dated</dt><dd>${fmtDate(i.date)}</dd>
        <dt>PO</dt><dd>${esc(i.po)}</dd>
        <dt>Terms</dt><dd class="${termsFlagged ? "is-flagged" : ""}">Net ${i.terms_days}</dd>
      </dl>
    </div>
    <table class="lines">
      <thead><tr><th>Particulars</th><th class="r hide-sm">Qty</th><th class="r hide-sm">Rate</th><th class="r">Amount</th></tr></thead>
      <tbody>${rows}</tbody>
      <tfoot>
        <tr><td class="label" colspan="3">Subtotal</td><td class="r">${money(i.subtotal)}</td></tr>
        <tr><td class="label" colspan="3">GST 18%</td><td class="r">${money(i.tax)}</td></tr>
        <tr><td class="label" colspan="3">Invoice total</td><td class="r">${money(i.total)}</td></tr>
      </tfoot>
    </table>
    <div class="sheet-actions">
      <p class="story">${esc(i.story)}</p>
      <button class="btn btn-ink" id="examine" type="button">${review ? "Examine again" : "Examine with memory"}</button>
    </div>
    <ol class="steps" id="steps" hidden></ol>`;
  // fix colspan on small screens where qty/rate are hidden
  if (matchMedia("(max-width: 760px)").matches) $("#sheet").querySelectorAll("tfoot .label").forEach((td) => td.colSpan = 1);
  $("#examine").onclick = () => examine(i.key);
}

// ── Before any review: show what's already remembered about the vendor ──
async function showKnown(i) {
  const v = vendorOf(i);
  $("#thread-sub").innerHTML = `Everything remembered about ${esc(v.short)}`;
  $("#timeline").innerHTML = `<li class="empty"><p class="empty-text">Checking Hindsight…</p></li>`;
  try {
    const { memories } = await api(`/api/vendor/${v.slug}/memory`);
    if (S.current !== i.key) return;
    $("#timeline").innerHTML = memories.length
      ? memories.map((m) => memItem(m, false)).join("")
      : `<li class="empty"><p class="empty-text">No memories of ${esc(v.short)} yet. This is a first encounter: LedgerMind can only check the arithmetic,
         and everything it learns starts with the decision you post.</p></li>`;
  } catch (e) {
    $("#timeline").innerHTML = `<li class="empty"><p class="error">${esc(e.message)}</p></li>`;
  }
}

function memItem(m, withRefs, cites = [], records = []) {
  const rec = records.find((r) => r.ref === m.record);
  const citedBy = cites.length ? `<span class="cited">cited by flag ${cites.join(", ")}</span>` : "";
  return `<li class="${cites.length ? "is-cited" : ""}" data-ref="${m.ref || ""}">
    <div class="mem-date">${withRefs ? `<span class="ref">${m.ref}</span>` : ""}${fmtDate(m.date)}</div>
    <p class="mem-text">${esc(m.text)}</p>
    <div class="mem-meta">
      <span class="kind ${m.type}">${m.type === "observation" ? "learned pattern" : m.type === "experience" ? "experience" : "fact"}</span>
      ${withRefs ? `<span title="Relevance ${m.score}"><span class="relevance"><i style="width:${Math.min(100, Math.round(m.score * 100))}%"></i></span></span>
      <span>via ${m.source === "both" ? "both queries" : m.source === "similar" ? "similar-issue search" : "vendor profile"}</span>` : ""}
      ${citedBy}
    </div>
    ${rec ? `<details class="record"><summary>Source record ${rec.ref}</summary><p>${esc(rec.text)}</p></details>` : ""}
  </li>`;
}

// ── Examine: recall → review (with + without memory) ─────────────────────
async function examine(key) {
  if (S.busy) return;
  S.busy = true;
  const i = inv(key), v = vendorOf(i);
  $("#examine").disabled = true;
  $("#verdict").hidden = true; $("#post").hidden = true; $("#posted").hidden = true;
  const steps = $("#steps");
  steps.hidden = false;
  const labels = [`Recalling ${v.short}'s billing history from Hindsight`, "Searching memory for past issues resembling these lines",
    "Reviewing with memory, and again without it, for comparison"];
  steps.innerHTML = labels.map((l) => `<li>${l}</li>`).join("");
  const lis = [...steps.children];
  let n = 0;
  lis[0].classList.add("is-on");
  const tick = setInterval(() => {
    if (n < lis.length - 1) { lis[n].classList.replace("is-on", "is-done"); lis[++n].classList.add("is-on"); }
  }, 900);
  $("#thread-sub").textContent = "Recalling…";
  try {
    const review = await api(`/api/analyze/${key}`, { method: "POST" });
    S.reviews[key] = review;
    clearInterval(tick);
    S.busy = false;
    if (S.current !== key) return;
    renderSheet(i, review);
    renderVerdict(i, review);
    renderThread(i, review);
  } catch (e) {
    clearInterval(tick);
    S.busy = false;
    steps.insertAdjacentHTML("afterend", `<p class="error">${esc(e.message)}</p>`);
    $("#examine").disabled = false;
  }
}

function citeMap(review) {
  const map = {};
  review.with_memory.flags.forEach((f, n) => (f.memory_refs || []).forEach((r) => (map[r] ||= []).push(n + 1)));
  // refs cited in the reasoning count too
  (review.with_memory.reasoning || "").replace(/\[(M\d+)\]/g, (_, r) => { map[r] ||= []; });
  return map;
}

function markRefs(text) {
  return esc(text).replace(/\[(M\d+)\]/g, `<mark data-ref="$1">$1</mark>`);
}

function renderVerdict(i, review) {
  const w = review.with_memory, s = review.stateless;
  const noMemory = review.memories.length === 0;
  const differs = w.verdict !== s.verdict;
  const flags = w.flags.map((f, n) => `
    <li class="flag" data-flag="${n + 1}" data-refs="${(f.memory_refs || []).join(" ")}">
      <span class="no">${n + 1}</span>
      <div><h3>${esc(f.title)}<span class="sev ${f.severity}">${f.severity}</span>${f.recurring ? `<span class="sev recurring">recurring</span>` : ""}</h3>
        <p>${markRefs(f.detail)}${(f.memory_refs || []).length ? ` <span class="cited">Memory: ${f.memory_refs.map((r) => `<mark data-ref="${r}">${r}</mark>`).join(" ")}</span>` : ""}</p></div>
      <span class="amt">${f.amount_at_risk ? money(f.amount_at_risk) : ""}</span>
    </li>`).join("");
  $("#verdict").innerHTML = `
    <div class="verdict-top">
      <div class="stamp ${w.verdict}">${VERDICT[w.verdict].toUpperCase()}</div>
      <div>
        <h2>${esc(w.headline)}</h2>
        <p class="reason">${markRefs(w.reasoning)}</p>
        <p class="action">${esc(w.recommended_action || "")}</p>
      </div>
    </div>
    ${flags ? `<ol class="flags">${flags}</ol>` : ""}
    <div class="compare">
      <div class="without"><h4>A stateless agent, no memory</h4><div class="v ${s.verdict}">${VERDICT[s.verdict]}</div><p>${esc(s.headline)}</p></div>
      <div class="with"><h4>LedgerMind, with ${review.memories.length} recalled ${review.memories.length === 1 ? "memory" : "memories"}</h4>
        <div class="v ${w.verdict}">${VERDICT[w.verdict]}${w.amount_at_risk ? ` · ${money(w.amount_at_risk)} at risk` : ""}</div><p>${w.flags.length} flag${w.flags.length === 1 ? "" : "s"} raised</p></div>
    </div>
    <p class="compare-note">${noMemory ? "First invoice from this vendor, so there is nothing to remember yet. Both agents see the same thing."
      : differs ? "Same invoice, same model. The only difference is memory." : "Memory confirms the invoice matches this vendor's history."}</p>`;
  $("#verdict").hidden = false;
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
  let html = `<li class="q"><div class="mem-date">recall() · ${Math.max(ms.profile, ms.similar)} ms</div>
    <p class="q-text">Two queries to bank <code>${esc(review.bank)}</code>, scoped to tag <code>vendor:${esc(v.slug)}</code>:<br>
    <q>${esc(q.profile)}</q><br><q>${esc(q.similar.slice(0, 140))}${q.similar.length > 140 ? "…" : ""}</q></p></li>`;
  html += review.memories.length
    ? review.memories.map((m) => memItem(m, true, cites[m.ref] || [], review.records)).join("")
    : `<li class="empty"><p class="empty-text">Nothing came back. LedgerMind has never seen ${esc(v.short)} before, so this invoice sets the baseline.</p></li>`;
  const r = S.retained[i.key];
  if (r) html += retainedItem(r);
  $("#timeline").innerHTML = html;
  $("#thread-sub").innerHTML = `Recalled before reviewing <b>${esc(i.number)}</b>`;
  bindHighlights();
}

function retainedItem(r) {
  return `<li class="w"><div class="mem-date">retain()${r.ms ? ` · ${r.ms} ms` : ""}</div>
    <p class="q-text">Written back to memory so the next invoice is judged against it:</p>
    <p class="w-text">${esc(r.content)}</p></li>`;
}

// hovering a flag or an [M#] mark lights up the memory it relied on
function bindHighlights() {
  document.querySelectorAll("mark[data-ref], .flag[data-refs]").forEach((el) => {
    const refs = el.dataset.ref ? [el.dataset.ref] : el.dataset.refs.split(" ").filter(Boolean);
    el.onmouseenter = () => refs.forEach((r) => document.querySelector(`#timeline li[data-ref="${r}"]`)?.classList.add("is-lit"));
    el.onmouseleave = () => document.querySelectorAll("#timeline li.is-lit").forEach((li) => li.classList.remove("is-lit"));
    el.onclick = () => document.querySelector(`#timeline li[data-ref="${refs[0]}"]`)?.scrollIntoView({ behavior: "smooth", block: "center" });
  });
}

// ── Post a decision → retain() ────────────────────────────────────────────
async function commit(decision) {
  const key = S.current;
  const buttons = document.querySelectorAll(".post-actions .btn");
  buttons.forEach((b) => (b.disabled = true));
  $("#post").querySelector(".error")?.remove();
  try {
    const res = await api(`/api/commit/${key}`, { method: "POST", body: JSON.stringify({ decision, note: $("#note").value }) });
    S.postings = res.postings;
    S.retained[key] = res.retained;
    $("#post").hidden = true;
    renderBook(); renderTally();
    renderThread(inv(key), S.reviews[key]);
    renderPosted(inv(key));
    $("#timeline").lastElementChild?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  } catch (e) {
    $("#post").insertAdjacentHTML("beforeend", `<p class="error">${esc(e.message)}</p>`);
  } finally {
    buttons.forEach((b) => (b.disabled = false));
  }
}

function renderPosted(i) {
  const p = posting(i.key);
  const box = $("#posted");
  if (!p) { box.hidden = true; return; }
  const next = S.invoices.find((x) => x.vendor === i.vendor && !posting(x.key));
  const disputed = p.decision !== "approve" && S.reviews[i.key];
  box.innerHTML = `
    <h3>Posted as ${STATUS[p.decision]}, and remembered</h3>
    <p>LedgerMind retained this invoice, its flags and your note in Hindsight. The next invoice from ${esc(vendorOf(i).short)} will be checked against it.</p>
    <div class="row">
      ${next ? `<button class="btn btn-ink" type="button" data-go="${next.key}">Open invoice ${S.invoices.filter((x) => x.vendor === i.vendor).indexOf(next) + 1}: ${esc(next.number)}</button>` : ""}
      ${disputed ? `<a class="btn" href="/api/dispute/${i.key}.pdf" target="_blank" rel="noopener">Dispute notice (PDF)</a>` : ""}
    </div>`;
  box.hidden = false;
  box.querySelector("[data-go]")?.addEventListener("click", (e) => select(e.target.dataset.go));
}

// ── Ask the ledger (reflect) ──────────────────────────────────────────────
async function ask(question) {
  const box = $("#answer");
  const v = vendorOf(inv(S.current));
  box.hidden = false;
  box.innerHTML = `<p class="empty-text">Reflecting on everything remembered about ${esc(v.short)}…</p>`;
  try {
    const r = await api("/api/ask", { method: "POST", body: JSON.stringify({ vendor: v.slug, question }) });
    const html = window.marked ? DOMPurify.sanitize(marked.parse(r.answer)) : esc(r.answer);
    box.innerHTML = html + (r.based_on.length ? `<p class="basis">Based on ${r.based_on.length} memories via Hindsight reflect()</p>` : "");
  } catch (e) {
    box.innerHTML = `<p class="error">${esc(e.message)}</p>`;
  }
}

// ── Wiring ────────────────────────────────────────────────────────────────
$("#vendors").addEventListener("click", (e) => { const t = e.target.closest(".inv-tab"); if (t) select(t.dataset.key); });
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
