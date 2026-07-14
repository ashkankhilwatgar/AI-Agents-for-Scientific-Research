# HHT ACMG Classifier — Browser GUI Demo

A human-in-the-loop browser demo that wraps the existing CLI pipeline
(`pipeline.py`) for HHT (Hereditary Hemorrhagic Telangiectasia) variant
classification. Every criterion is a checkbox you can freely toggle, variable-
strength criteria get a strength selector, and the classification recalculates
live on every change.

## Run it

From the **repo root**, using the project venv (so pipeline imports resolve):

```bash
venv/bin/python -m gui.server
```

Then open <http://127.0.0.1:8000>.

Environment overrides: `HHT_GUI_HOST` (default `127.0.0.1`), `HHT_GUI_PORT`
(default `8000`).

No extra dependencies — the server is built on Python's stdlib `http.server`.

## How it works

The backend does **not** re-implement any rules. It reads criterion metadata
and exclusion reasons straight from `data/planrag.py` (`PLANRAG_DB`,
`EXCLUDED_CRITERIA`, and the `SCORING` block), and scores the current
checkbox/strength state by calling the real `tools.scoring.classify()`. So the
live classification is identical to what the CLI pipeline would compute — same
combining rules, same PM1+PM5 incompatibility downgrade, same order of
precedence (benign → pathogenic → likely pathogenic → likely benign → VUS).

Pre-population of the checkboxes comes from a pipeline run in one of two modes:

- **Cached** (default): loads the best existing per-variant JSON from
  `outputs/` — instant. The dropdown lists every HHT variant that has a cached
  run (best = most complete result, then most recent).
- **Live**: enter any variant and click *Run pipeline* to execute
  `pipeline.run_pipeline()` end-to-end. This is slow (LLM + external API calls,
  can take minutes) and needs the API keys in `.env`.

> First cached load can be slow if the repo lives on an iCloud/network volume
> (files are materialised on first read). The scan is memoised, so it only pays
> that cost once per server run.

Deep link: `http://127.0.0.1:8000/#variant=NM_000020.3:c.1120C>T` (optionally
`&mode=live`) auto-loads a variant on open.

## The three criterion groups

- **Automatable** (13): `PM2_SUPPORTING, BA1, BS1, PS4, PM1, PVS1, PM5, PS3,
  PS1, PP3, PM4, BP4, BP7` — pre-set from the pipeline, fully editable.
- **Manual-input** (5): `BP5, BP2, PP4_MODERATE, PP1, BS4` — need patient data
  the pipeline can't fetch. Use the *Manual data entry* panel to type the data
  each rule requires (synthetic is fine); it becomes that criterion's evidence.
  Then toggle apply/not-apply yourself.
- **Excluded** (8): shown greyed-out with the exclusion reason from
  `EXCLUDED_CRITERIA`; cannot be applied.

Variable-strength criteria (`PVS1, PS3, PS4, PM5, PP1` pathogenic; `BS1`
benign) show a strength selector next to their checkbox, used only when checked.

## HTTP API

| Method | Route | Purpose |
|--------|-------|---------|
| GET  | `/api/meta`   | Criterion groupings + strength options + exclusion reasons (from planrag) |
| GET  | `/api/cached` | HHT variants that have a cached run |
| POST | `/api/run`    | `{variant, mode}` → per-criterion pre-population + initial score |
| POST | `/api/score`  | `{state: {KEY: {applies, applied_strength}}}` → `classify()` result |

## Files

- `server.py` — stdlib HTTP backend (metadata, cached-run index, scoring).
- `static/index.html`, `static/styles.css`, `static/app.js` — the GUI.
