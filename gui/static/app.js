"use strict";

// ── Client state ──────────────────────────────────────────────────────────
const state = {
  meta: null,                 // /api/meta payload
  metaByKey: {},              // key -> criterion meta
  criteria: {},               // key -> { applies, applied_strength, evidence, reasoning, status, note }
  manualEvidence: {},         // key -> user-typed patient data (manual criteria)
  variant: null,
  automatableUnlocked: false, // automatable checkboxes are read-only until "Review" is clicked
};

const $ = (sel) => document.querySelector(sel);
const el = (tag, cls, txt) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (txt != null) n.textContent = txt;
  return n;
};

async function api(path, opts) {
  const res = await fetch(path, opts);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

function setStatus(msg, kind) {
  const bar = $("#status-bar");
  if (!msg) { bar.classList.add("hidden"); return; }
  bar.className = `status-bar ${kind || "info"}`;
  bar.textContent = msg;
}

// ── Bootstrap ──────────────────────────────────────────────────────────────
async function init() {
  state.meta = await api("/api/meta");
  for (const c of [...state.meta.automatable, ...state.meta.manual]) state.metaByKey[c.key] = c;

  renderExcluded();
  populateManualSelect();
  populateEvidenceSelect();

  // Empty initial criteria state so the panels render before a variant loads.
  const blank = {};
  for (const c of [...state.meta.automatable, ...state.meta.manual]) {
    blank[c.key] = {
      applies: false,
      applied_strength: c.default_strength || null,
      evidence: "", reasoning: "", status: "not_evaluated", note: "",
    };
  }
  state.criteria = blank;
  renderCriteria();

  await loadCachedList();

  // Deep link: #variant=NM_000020.3:c.1120C>T[&mode=cached|live] auto-loads on open.
  const hash = new URLSearchParams(location.hash.slice(1));
  const deepVariant = hash.get("variant");
  if (deepVariant) {
    const mode = hash.get("mode") === "live" ? "live" : "cached";
    $("#cached-select").value = deepVariant;
    loadVariant(deepVariant, mode);
  }

  $("#load-cached").addEventListener("click", onLoadCached);
  $("#run-live").addEventListener("click", onRunLive);
  $("#manual-select").addEventListener("change", onManualSelectChange);
  $("#manual-save").addEventListener("click", onManualSave);
  $("#evidence-select").addEventListener("change", renderEvidence);
  $("#review-automatable").addEventListener("click", onReviewAutomatable);
  $("#disease-select").addEventListener("change", onDiseaseChange);
  updateReviewButton();
}

// ── Disease selector ───────────────────────────────────────────────────────
// Only HHT is implemented; the "coming soon" option signals future scope but
// changes nothing. Selecting it reverts to HHT so app state stays consistent.
function onDiseaseChange() {
  const sel = $("#disease-select");
  if (sel.value !== "HHT") {
    sel.value = "HHT";
    setStatus("More disease support is coming soon — this demo currently supports HHT only.", "info");
  }
}

// ── Automatable editing lock ─────────────────────────────────────────────────
function onReviewAutomatable() {
  state.automatableUnlocked = !state.automatableUnlocked;
  updateReviewButton();
  renderCriteria();
  setStatus(
    state.automatableUnlocked
      ? "Automatable criteria unlocked — you can now override the pipeline's calls. Review each criterion's evidence before toggling."
      : "Automatable criteria re-locked — editing disabled.",
    "info"
  );
}

function updateReviewButton() {
  const btn = $("#review-automatable");
  if (!btn) return;
  if (state.automatableUnlocked) {
    btn.textContent = "Lock Automatable Criteria";
    btn.classList.add("active");
  } else {
    btn.textContent = "Review Automatable Criteria";
    btn.classList.remove("active");
  }
}

// ── Variant loading ──────────────────────────────────────────────────────────
async function loadCachedList() {
  try {
    const { variants } = await api("/api/cached");
    const sel = $("#cached-select");
    sel.innerHTML = "";
    if (!variants.length) {
      sel.appendChild(new Option("— no cached runs found —", ""));
      return;
    }
    for (const v of variants) {
      const cls = v.classification ? ` — ${v.classification}` : "";
      sel.appendChild(new Option(`${v.variant}${cls}`, v.variant));
    }
  } catch (e) {
    setStatus(`Could not list cached runs: ${e.message}`, "error");
  }
}

async function onLoadCached() {
  const variant = $("#cached-select").value;
  if (!variant) return;
  await loadVariant(variant, "cached");
}

async function onRunLive() {
  const variant = $("#live-variant").value.trim();
  if (!variant) { setStatus("Enter a variant to run live.", "error"); return; }
  await loadVariant(variant, "live");
}

async function loadVariant(variant, mode) {
  const btns = [$("#load-cached"), $("#run-live")];
  btns.forEach((b) => (b.disabled = true));
  setStatus(
    mode === "live"
      ? `Running the full pipeline for ${variant} — this can take a few minutes…`
      : `Loading cached run for ${variant}…`,
    "busy"
  );
  try {
    const data = await api("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ variant, mode }),
    });
    state.variant = variant;
    state.criteria = data.criteria;
    // A fresh run re-locks the automatable criteria — they must be reviewed again.
    state.automatableUnlocked = false;
    updateReviewButton();
    // Seed manual-evidence store with any evidence the pipeline produced.
    state.manualEvidence = {};
    for (const key of Object.keys(state.criteria)) {
      if (state.metaByKey[key]?.group === "manual" && state.criteria[key].evidence) {
        state.manualEvidence[key] = state.criteria[key].evidence;
      }
    }
    renderCriteria();
    renderScoring(data.scoring);
    renderEvidence();
    onManualSelectChange();
    const ref = data.pipeline_score?.classification;
    setStatus(
      `Loaded ${variant} (${mode}). Pipeline classified it as: ${ref || "—"}. ` +
      `Toggle any criterion to explore — scoring updates live.`,
      "info"
    );
  } catch (e) {
    setStatus(`Failed to load ${variant}: ${e.message}`, "error");
  } finally {
    btns.forEach((b) => (b.disabled = false));
  }
}

// ── Rendering: criteria ───────────────────────────────────────────────────────
function badgeFor(meta) {
  if (meta.is_variable) {
    return el("span", `badge ${meta.category === "Benign" ? "benign" : "path"}`,
      meta.category === "Benign" ? "Benign · variable" : "Pathogenic · variable");
  }
  const label = state.meta.strength_labels[meta.fixed_bucket] || meta.fixed_bucket || "fixed";
  return el("span", "badge fixed", label);
}

// Automatable criteria are read-only until "Review Automatable Criteria" is clicked.
// Manual criteria are read-only until the user has entered patient data for them.
// Everything else follows from those two rules.
function isLocked(meta) {
  if (meta.group === "manual") return !state.manualEvidence[meta.key];
  return !state.automatableUnlocked;
}

function critRow(meta) {
  const c = state.criteria[meta.key];
  const locked = isLocked(meta);
  const row = el("div", "crit" + (c.applies ? " applied" : "") + (locked ? " locked" : ""));

  const cb = el("input");
  cb.type = "checkbox";
  cb.checked = !!c.applies;
  cb.disabled = locked;
  cb.addEventListener("change", () => {
    c.applies = cb.checked;
    renderCriteria();
    rescore();
  });

  const main = el("div", "crit-main");
  const name = el("div", "crit-name");
  name.appendChild(el("span", null, meta.name));
  name.appendChild(badgeFor(meta));
  main.appendChild(name);
  main.appendChild(el("div", "crit-desc", meta.description || meta.threshold || ""));

  // status / evidence flags
  if (c.status === "error") main.appendChild(el("span", "crit-flag err", c.note || "pipeline error"));
  else if (c.status === "skipped") main.appendChild(el("span", "crit-flag skip", c.note || "skipped"));
  if (meta.group === "manual") {
    const hasEv = !!state.manualEvidence[meta.key];
    main.appendChild(el("span", `crit-flag ${hasEv ? "evidence-set" : "manual"}`,
      hasEv ? "patient data entered ✓" : "needs patient data"));
  }

  // strength selector (variable-strength criteria only, relevant when checked)
  const strengthActive = c.applies && !locked;
  const strengthWrap = el("div", "strength-sel" + (strengthActive ? "" : " disabled"));
  if (meta.is_variable) {
    strengthWrap.appendChild(el("span", "lbl", "Strength"));
    const sel = el("select");
    for (const opt of meta.strength_options) {
      const o = new Option(opt.label, opt.value);
      if (opt.value === c.applied_strength) o.selected = true;
      sel.appendChild(o);
    }
    sel.disabled = !strengthActive;
    sel.addEventListener("change", () => {
      c.applied_strength = sel.value;
      rescore();
    });
    strengthWrap.appendChild(sel);
  }

  row.appendChild(cb);
  row.appendChild(main);
  row.appendChild(strengthWrap);
  return row;
}

function renderCriteria() {
  const auto = $("#automatable-list");
  const man = $("#manual-list");
  auto.innerHTML = "";
  man.innerHTML = "";
  for (const meta of state.meta.automatable) auto.appendChild(critRow(meta));
  for (const meta of state.meta.manual) man.appendChild(critRow(meta));
}

function renderExcluded() {
  const box = $("#excluded-list");
  box.innerHTML = "";
  for (const ex of state.meta.excluded) {
    const row = el("div", "crit");
    const name = el("div", "crit-name", ex.key);
    row.appendChild(name);
    row.appendChild(el("div", "crit-reason", ex.reason));
    box.appendChild(row);
  }
}

// ── Rendering: scoring ─────────────────────────────────────────────────────────
const BUCKET_LABELS = {
  vs: "Very Strong (P)", s: "Strong (P)", m: "Moderate (P)", sup: "Supporting (P)",
  ba: "Stand-alone (B)", bs: "Strong (B)", bsup: "Supporting (B)",
};

function renderScoring(scoring) {
  const label = $("#verdict-label");
  const rule = $("#verdict-rule");
  const verdict = $("#verdict");
  const cls = scoring.classification || "—";
  label.textContent = cls;
  rule.textContent = scoring.rule_matched || "";
  // map classification to a css class
  const key = cls.replace(/\(.*\)/, "").trim().replace(/\s+/g, "-");
  verdict.className = "verdict " + (cls.includes("VUS") ? "VUS" : key);

  const buckets = $("#buckets");
  buckets.innerHTML = "";
  const counts = scoring.buckets || {};
  for (const k of ["vs", "s", "m", "sup", "ba", "bs", "bsup"]) {
    const n = counts[k] || 0;
    const b = el("div", "bucket" + (n > 0 ? " nonzero" : ""));
    b.appendChild(el("span", null, BUCKET_LABELS[k]));
    b.appendChild(el("span", "n", String(n)));
    buckets.appendChild(b);
  }

  const notes = $("#incompat-notes");
  notes.innerHTML = "";
  for (const note of scoring.incompatibility_notes || []) notes.appendChild(el("div", "note", "⚠ " + note));
  for (const u of scoring.unrecognised_criteria || []) notes.appendChild(el("div", "note", "⚠ unrecognised: " + u));
}

let rescoreTimer = null;
function rescore() {
  clearTimeout(rescoreTimer);
  rescoreTimer = setTimeout(async () => {
    const payload = {};
    for (const [key, c] of Object.entries(state.criteria)) {
      payload[key] = { applies: !!c.applies, applied_strength: c.applied_strength };
    }
    try {
      const scoring = await api("/api/score", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ state: payload }),
      });
      renderScoring(scoring);
    } catch (e) {
      setStatus(`Scoring error: ${e.message}`, "error");
    }
  }, 60);
}

// ── Manual data entry ─────────────────────────────────────────────────────────
function populateManualSelect() {
  const sel = $("#manual-select");
  sel.innerHTML = "";
  for (const c of state.meta.manual) sel.appendChild(new Option(`${c.name}`, c.key));
}

function onManualSelectChange() {
  const key = $("#manual-select").value;
  const meta = state.metaByKey[key];
  const req = $("#manual-requirement");
  req.textContent = meta ? (meta.threshold || meta.description || "Enter the data this criterion requires.") : "";
  $("#manual-text").value = state.manualEvidence[key] || "";
}

function onManualSave() {
  const key = $("#manual-select").value;
  if (!key) return;
  const text = $("#manual-text").value.trim();
  state.manualEvidence[key] = text;
  if (state.criteria[key]) {
    state.criteria[key].evidence = text;      // becomes this criterion's evidence
    state.criteria[key].reasoning = "Manually entered patient data.";
  }
  renderCriteria();
  renderEvidence();
  setStatus(`Saved evidence for ${state.metaByKey[key].name}. Toggle its checkbox to apply it.`, "info");
}

// ── Evidence viewer ─────────────────────────────────────────────────────────
function populateEvidenceSelect() {
  const sel = $("#evidence-select");
  sel.innerHTML = "";
  sel.appendChild(new Option("— select —", ""));
  for (const c of [...state.meta.automatable, ...state.meta.manual]) {
    sel.appendChild(new Option(`${c.name} (${c.group === "manual" ? "manual" : "auto"})`, c.key));
  }
}

function renderEvidence() {
  const key = $("#evidence-select").value;
  const body = $("#evidence-body");
  if (!key) { body.textContent = "Select a criterion to view its evidence."; return; }
  const c = state.criteria[key];
  const meta = state.metaByKey[key];
  body.innerHTML = "";

  const verdict = el("div", "ev-block");
  verdict.appendChild(el("div", "ev-label", "Current state"));
  const applyTxt = c.applies ? "APPLIES" : "does not apply";
  const strengthTxt = meta.is_variable && c.applies ? ` · ${state.meta.strength_labels[c.applied_strength] || c.applied_strength}` : "";
  verdict.appendChild(el("div", "ev-verdict", applyTxt + strengthTxt));
  body.appendChild(verdict);

  const evText = meta.group === "manual" ? (state.manualEvidence[key] || "") : (c.evidence || "");
  const ev = el("div", "ev-block");
  ev.appendChild(el("div", "ev-label", meta.group === "manual" ? "Patient data (entered)" : "Evidence"));
  ev.appendChild(el("div", null, evText || (meta.group === "manual" ? "No data entered yet." : "No evidence recorded.")));
  body.appendChild(ev);

  if (c.reasoning) {
    const rs = el("div", "ev-block");
    rs.appendChild(el("div", "ev-label", "Reasoning"));
    rs.appendChild(el("div", null, c.reasoning));
    body.appendChild(rs);
  }
  if (c.note) {
    const nt = el("div", "ev-block");
    nt.appendChild(el("div", "ev-label", "Note"));
    nt.appendChild(el("div", null, c.note));
    body.appendChild(nt);
  }
}

init().catch((e) => setStatus(`Startup error: ${e.message}`, "error"));
