"""
HHT ACMG Pipeline — Browser GUI Demo backend.

A dependency-free local server (stdlib http.server) that wraps the existing
CLI pipeline. It:

  * reads criterion metadata / exclusion reasons straight from
    data.classification_guidelines (HHT_CRITERIA_DB, EXCLUDED_CRITERIA, the SCORING block), so the
    GUI always reflects the real HHT VCEP rules; and
  * scores the current human-edited checkbox/strength state by calling the
    real tools.scoring.classify() — NOT a reimplemented point system — so the
    live classification is guaranteed identical to the CLI pipeline's.

Pre-population of the checkboxes comes from a pipeline run, either:
  * "cached"  — read an existing per-variant JSON from outputs/ (instant), or
  * "live"    — call pipeline.run_pipeline() for an arbitrary variant (slow;
                needs API keys + network).

Run:  python -m gui.server           (from the repo root, using the venv)
      then open http://127.0.0.1:8000
"""

from __future__ import annotations

import glob
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

# Make sure the repo root is importable when launched as a script.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from data.classification_guidelines import HHT_CRITERIA_DB, EXCLUDED_CRITERIA, query as guideline_query  # noqa: E402
from tools.scoring import classify  # noqa: E402

_STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
_OUTPUTS_DIR = os.path.join(_REPO_ROOT, "outputs")
DISEASE = "HHT"  # this demo is hardcoded to HHT per spec

# ── Criterion display groups (authoritative list from the demo spec) ──────────
AUTOMATABLE = [
    "PM2_SUPPORTING", "BA1", "BS1", "PS4", "PM1", "PVS1",
    "PM5", "PS3", "PS1", "PP3", "PM4", "BP4", "BP7",
]
MANUAL = ["BP5", "BP2", "PP4_MODERATE", "PP1", "BS4"]

# Variable-strength criteria (spec): PVS1, PS3, PS4, PM5, PP1, BS1.
# Their bucket depends on the user-selected applied_strength. Everything else is
# fixed-strength (see SCORING.fixed_strengths) and needs no strength selector.
_PATH_STRENGTHS = ["very_strong", "strong", "moderate", "supporting"]
_BENIGN_STRENGTHS = ["benign_strong", "benign_supporting"]
_VARIABLE_DEFAULTS = {
    "PVS1": "very_strong",
    "PS4":  "strong",
    "PS3":  "strong",
    "PM5":  "moderate",
    "PP1":  "supporting",
    "BS1":  "benign_supporting",
}
STRENGTH_LABELS = {
    "very_strong":       "Very Strong",
    "strong":            "Strong",
    "moderate":          "Moderate",
    "supporting":        "Supporting",
    "benign_strong":     "Benign Strong",
    "benign_supporting": "Benign Supporting",
    "benign_stand_alone": "Benign Stand-alone",
    "stand_alone":       "Stand-alone",
}


def _scoring() -> dict:
    return guideline_query("SCORING", disease=DISEASE) or {}


def _normalise_key(criterion: str) -> str:
    """Pipeline result 'criterion' fields vary (e.g. 'PM2_Supporting' vs 'PVS1').
    Normalise to the uppercase HHT_CRITERIA_DB key used everywhere else."""
    return (criterion or "").upper().replace("-", "_").replace(" ", "_")


def _criterion_meta(key: str, group: str) -> dict:
    """Build the front-end metadata blob for one criterion."""
    entry = HHT_CRITERIA_DB.get(key, {})
    fixed = _scoring().get("fixed_strengths", {})
    is_variable = key not in fixed
    is_benign = (entry.get("acmg_category") == "Benign") or key.startswith("B")

    meta = {
        "key":          key,
        "name":         entry.get("criterion", key),
        "group":        group,                       # automatable | manual
        "category":     entry.get("acmg_category", "Benign" if is_benign else "Pathogenic"),
        "description":  (entry.get("description") or "").strip(),
        "threshold":    (entry.get("threshold") or "").strip(),
        "is_variable":  is_variable,
        "fixed_bucket": None if is_variable else fixed.get(key),
    }
    if is_variable:
        options = _BENIGN_STRENGTHS if is_benign else _PATH_STRENGTHS
        meta["strength_options"] = [{"value": v, "label": STRENGTH_LABELS.get(v, v)} for v in options]
        meta["default_strength"] = _VARIABLE_DEFAULTS.get(key, options[0])
    return meta


def build_meta() -> dict:
    """Return the guideline metadata needed to render the front end."""
    excluded = [{"key": k, "reason": v} for k, v in EXCLUDED_CRITERIA.items()]
    return {
        "disease":        DISEASE,
        "automatable":    [_criterion_meta(k, "automatable") for k in AUTOMATABLE],
        "manual":         [_criterion_meta(k, "manual") for k in MANUAL],
        "excluded":       excluded,
        "strength_labels": STRENGTH_LABELS,
    }


# ── Reading pipeline output for pre-population ────────────────────────────────

def _iter_result_files():
    """Yield (path, parsed) for every per-variant result JSON under outputs/."""
    for path in glob.glob(os.path.join(_OUTPUTS_DIR, "**", "*.json"), recursive=True):
        if os.path.basename(path) == "batch_summary.json" or path.endswith(".error.json"):
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict) and data.get("variant") and isinstance(data.get("results"), list):
            yield path, data


def _complete_count(data: dict) -> int:
    return sum(1 for r in data.get("results", []) if r.get("status") == "complete")


# The outputs/ scan is memoised: it can be slow on the first hit (e.g. when the
# repo lives on an iCloud/network volume and files must be materialised on
# read), but the tree only changes when the pipeline runs, so once per server
# process is plenty. Call build_index(force=True) to rescan.
_INDEX: dict[str, tuple] | None = None


def build_index(force: bool = False) -> dict[str, tuple]:
    """variant -> (score, path, data) for the best cached run of each variant.
    'best' = most complete results, then most recently modified."""
    global _INDEX
    if _INDEX is not None and not force:
        return _INDEX
    best: dict[str, tuple] = {}
    for path, data in _iter_result_files():
        variant = data["variant"]
        score = (_complete_count(data), os.path.getmtime(path))
        if variant not in best or score > best[variant][0]:
            best[variant] = (score, path, data)
    _INDEX = best
    return _INDEX


def list_cached() -> list[dict]:
    """HHT variants that have a cached run, best run per variant.
    Filtered to HHT because this demo scores everything with the HHT VCEP rules."""
    out = []
    for variant, (score, path, data) in build_index().items():
        if (data.get("disease") or "").upper() != DISEASE:
            continue
        out.append({
            "variant":        variant,
            "disease":        data.get("disease", DISEASE),
            "classification": data.get("classification"),
            "complete":       score[0],
            "file":           os.path.relpath(path, _REPO_ROOT),
        })
    out.sort(key=lambda r: (-r["complete"], r["variant"]))
    return out


def _load_best_cached(variant: str) -> dict | None:
    entry = build_index().get(variant)
    return entry[2] if entry else None


def _prepopulate_from_results(results: list[dict]) -> dict:
    """Turn a pipeline results list into per-criterion GUI pre-population state."""
    by_key = {}
    for r in results:
        by_key[_normalise_key(r.get("criterion"))] = r

    criteria = {}
    for key in AUTOMATABLE + MANUAL:
        r = by_key.get(key)
        entry = {
            "applies":          False,
            "applied_strength": _VARIABLE_DEFAULTS.get(key),
            "evidence":         "",
            "reasoning":        "",
            "status":           "not_evaluated",
            "note":             "",
        }
        if r:
            status = r.get("status")
            entry["status"] = status or "complete"
            entry["evidence"] = r.get("evidence") or ""
            entry["reasoning"] = r.get("reasoning") or ""
            if status == "error":
                entry["note"] = f"Pipeline error: {r.get('error', 'unknown')}"
            elif status == "skipped":
                entry["note"] = f"Skipped: {r.get('reason', 'unknown')}"
            else:
                entry["applies"] = bool(r.get("applies"))
                if r.get("applied_strength"):
                    entry["applied_strength"] = r["applied_strength"]
        elif key in MANUAL:
            entry["note"] = "Manual-input criterion — enter patient data below."
        criteria[key] = entry
    return criteria


def _score_state(state: dict) -> dict:
    """Build a results_dict from GUI state and run the real classify()."""
    fixed = _scoring().get("fixed_strengths", {})
    results_dict = {}
    for key, s in state.items():
        if not s.get("applies"):
            continue
        # Fixed-strength criteria: classify() ignores applied_strength and uses
        # the fixed bucket. Variable ones: pass through the user's selection.
        applied_strength = s.get("applied_strength") if key not in fixed else fixed.get(key)
        results_dict[key] = {
            "applies":          True,
            "status":           "complete",
            "applied_strength": applied_strength,
        }
    return classify(results_dict, disease=DISEASE)


def run_pipeline_for(variant: str, mode: str) -> dict:
    if mode == "live":
        from pipeline import run_pipeline  # lazy: pulls in the whole LLM stack
        results, scoring_result = run_pipeline(variant, DISEASE)
    else:
        data = _load_best_cached(variant)
        if data is None:
            raise FileNotFoundError(f"No cached run found for {variant}")
        results = data["results"]
        scoring_result = data.get("scoring")

    criteria = _prepopulate_from_results(results)
    # Re-score from the pre-populated state so the panel is consistent with the
    # checkboxes shown (rather than trusting a possibly-stale saved score).
    initial = _score_state({k: {"applies": v["applies"], "applied_strength": v["applied_strength"]}
                            for k, v in criteria.items()})
    return {
        "variant":        variant,
        "disease":        DISEASE,
        "mode":           mode,
        "criteria":       criteria,
        "scoring":        initial,
        "pipeline_score": scoring_result,  # the pipeline's own saved classification, for reference
    }


# ── HTTP handler ──────────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    server_version = "HHTDemo/1.0"

    def _send_json(self, obj, status=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path, content_type):
        try:
            with open(path, "rb") as fh:
                body = fh.read()
        except OSError:
            self._send_json({"error": "not found"}, status=404)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0) or 0)
        if not length:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw or b"{}")
        except json.JSONDecodeError:
            return {}

    def do_GET(self):
        route = urlparse(self.path).path
        if route in ("/", "/index.html"):
            self._send_file(os.path.join(_STATIC_DIR, "index.html"), "text/html; charset=utf-8")
        elif route == "/static/app.js":
            self._send_file(os.path.join(_STATIC_DIR, "app.js"), "application/javascript; charset=utf-8")
        elif route == "/static/styles.css":
            self._send_file(os.path.join(_STATIC_DIR, "styles.css"), "text/css; charset=utf-8")
        elif route == "/api/meta":
            self._send_json(build_meta())
        elif route == "/api/cached":
            self._send_json({"variants": list_cached()})
        else:
            self._send_json({"error": f"unknown route {route}"}, status=404)

    def do_POST(self):
        route = urlparse(self.path).path
        body = self._read_json_body()
        try:
            if route == "/api/run":
                variant = (body.get("variant") or "").strip()
                mode = body.get("mode", "cached")
                if not variant:
                    self._send_json({"error": "variant is required"}, status=400)
                    return
                self._send_json(run_pipeline_for(variant, mode))
            elif route == "/api/score":
                state = body.get("state") or {}
                self._send_json(_score_state(state))
            else:
                self._send_json({"error": f"unknown route {route}"}, status=404)
        except FileNotFoundError as e:
            self._send_json({"error": str(e)}, status=404)
        except Exception as e:  # keep the demo alive; surface the message
            self._send_json({"error": f"{type(e).__name__}: {e}"}, status=500)

    def log_message(self, fmt, *args):  # quieter console
        sys.stderr.write("  %s - %s\n" % (self.address_string(), fmt % args))


def main():
    host = os.environ.get("HHT_GUI_HOST", "127.0.0.1")
    port = int(os.environ.get("HHT_GUI_PORT", "8000"))
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"HHT ACMG demo GUI  →  http://{host}:{port}")
    print("Press Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping.")
        httpd.shutdown()


if __name__ == "__main__":
    main()
