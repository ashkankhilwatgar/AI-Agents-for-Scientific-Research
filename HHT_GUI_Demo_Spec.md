# HHT ACMG Pipeline — Browser GUI Demo Spec (for Fable 5)

## Goal
Wrap the existing CLI pipeline (ACMG/AMP variant classification for HHT, using
the ACVRL1/ENG PlanRAG rules in `data/planrag.py`) in a simple browser GUI demo.
Human-in-the-loop: every criterion gets a checkbox the user can freely toggle,
and a live scoring panel recalculates the classification on every change.

## Integration
- Whatever is simplest: a small local backend (Flask/FastAPI in Python, since
  the pipeline is Python) that the browser calls over HTTP, OR the backend
  shells out to the existing CLI as a subprocess and parses its output.
  No need to over-engineer this — it's a demo.
- The frontend is plain HTML/JS (or a minimal React setup) running in the browser.

## Disease scope
Hardcode this demo to HHT (Hereditary Hemorrhagic Telangiectasia) only, using the
rules defined in `data/planrag.py` (`PLANRAG_DB`, `EXCLUDED_CRITERIA`, and the
`SCORING` block).

## Criteria to display

### Automatable criteria (evaluated by the pipeline, shown with evidence)
Pull these from `PLANRAG_DB` in `data/planrag.py`:
- PM2_SUPPORTING
- BA1
- BS1
- PS4
- PM1
- PVS1
- PM5
- PS3
- PS1
- PP3
- PM4
- BP4
- BP7

Each should render as a checkbox (checked = criterion applies, unchecked = does
not apply) pre-populated from the pipeline's output, but fully editable by the
user.

### Manual-input criteria (require patient data, human-entered)
These 5 criteria need patient-specific data the pipeline can't fetch on its own.
Give the user a dropdown to pick one of these 5, then a text box to enter
whatever data that criterion's rule (in `PLANRAG_DB`) requires. Data can be
fake/synthetic, just needs to be enough to let the user manually decide
apply/not-apply. After entry, the criterion still gets a checkbox like the rest.
- BP5
- BP2
- PP4_MODERATE
- PP1
- BS4

### Excluded criteria (must be shown, but disabled/greyed out, with the reason)
Pull directly from `EXCLUDED_CRITERIA` in `data/planrag.py` — do not let the user
apply these, but display them with their exclusion reason so it's clear why
they're missing:
- PS2 — Not Applicable per HHT VCEP (de novo variants rare in HHT; mosaicism observed)
- PM3 — Not Applicable per HHT VCEP (HHT is autosomal dominant; AR trans not relevant)
- PM6 — Not Applicable per HHT VCEP (de novo variants rare; should be confirmed not presumed)
- PP5 — Not Applicable per ClinGen SVI VCEP Review Committee
- BS2 — Not Applicable per HHT VCEP (full penetrance at early age not observed in HHT)
- BP1 — Not Applicable per HHT VCEP (missense variants common in HHT genes)
- BP3 — Not Applicable per HHT VCEP
- BP6 — Not Applicable per ClinGen SVI VCEP Review Committee

## Evidence section
- A dropdown listing all applicable (non-excluded) criteria.
- Selecting a criterion displays the evidence the pipeline produced for it
  (the text/reasoning that led it to apply or not apply), pulled from the
  pipeline's run output for that criterion.
- For the 5 manual-input criteria, this section shows whatever patient data the
  user typed in as the "evidence."

## Live scoring section
Implement using the exact combining rules in `PLANRAG_DB["SCORING"]`
(`data/planrag.py`), not a generic/simplified point system:

- Fixed-strength criteria buckets (from `SCORING.fixed_strengths`):
  - Supporting: PM2_SUPPORTING, PP3
  - Moderate: PP4_MODERATE, PM1, PM4
  - Strong: PS1, PS2 (excluded, ignore)
  - Benign standalone: BA1
  - Benign supporting: BS3_SUPPORTING, BP2, BP4, BP5, BP7
  - Benign strong: BS4
- Variable-strength criteria (from `SCORING.variable_strength_map`), whose
  bucket depends on an `applied_strength` value (very_strong / strong /
  moderate / supporting, or benign_strong / benign_supporting for BS1):
  PVS1, PS3, PS4, PM5, PP1, BS1
  - For this demo, expose a simple strength selector next to these criteria's
    checkbox (only relevant when checked) so the user can pick the strength
    level themselves.
- Incompatible combination rule: if both PM1 and PM5 are checked and PM5's
  strength is "strong", PM5 is auto-downgraded to "moderate" before scoring
  (per `SCORING.incompatible_combinations`).
- Classification logic, checked in this order — benign rules first, then
  pathogenic rules, first match wins:
  1. **Benign**: BA1 alone, OR ≥2 Strong benign
  2. **Likely Benign**: (1 Strong benign + 1 Supporting benign), OR 1 Strong
     benign alone, OR ≥2 Supporting benign
  3. **Pathogenic**: PVS1 + ≥1 Strong; OR PVS1 + ≥2 Moderate; OR PVS1 + 1
     Moderate + 1 Supporting; OR PVS1 + ≥2 Supporting; OR ≥2 Strong; OR 1
     Strong + ≥3 Moderate; OR 1 Strong + 2 Moderate + ≥2 Supporting; OR 1
     Strong + 1 Moderate + ≥4 Supporting
  4. **Likely Pathogenic**: PVS1 + 1 Moderate; OR PVS1 + 1 Supporting; OR 1
     Strong + 2 Moderate; OR 1 Strong + 1 Moderate; OR 1 Strong + ≥2
     Supporting; OR ≥3 Moderate; OR 2 Moderate + ≥2 Supporting; OR 1 Moderate +
     ≥4 Supporting
  5. Otherwise: **VUS** (Variant of Uncertain Significance)
- This recalculates live, instantly, every time any checkbox or strength
  selector changes — no submit button needed for scoring.
- Show which rule matched (e.g. "≥2 Strong") next to the resulting
  classification, for transparency.

## Human-in-the-loop principle
- Every checkbox starts pre-set from the pipeline's automated run, but the
  user can freely check/uncheck any non-excluded criterion at any time.
- The scoring section must always reflect the current checkbox/strength state,
  not the original pipeline output.

## Open items I still need from you before build
- Confirm which local backend approach you want to actually run this (Flask
  subprocess call to the CLI vs. direct Python import of the pipeline module) —
  or if you want me to just decide when we get to implementation.
- Whether there's a specific existing CLI entrypoint/script name Fable 5 should
  call, and what its expected input (gene, variant, transcript) and output
  format look like.
