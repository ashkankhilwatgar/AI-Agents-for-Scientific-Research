# Zero-tool LLM baseline

Runs a "closed-book" Gemini baseline for HHT variant classification, given the HHT
VCEP rules as a prompt and asked to classify each variant using *only* its own
knowledge — no tool calls, no web search. This exists to answer "does the
tool-augmented agent pipeline add value over just asking the model?" For a
model-controlled comparison, configure the main pipeline to use Gemini too.

See `run_baseline.py`'s module docstring for the full design rationale
(Gemini model control, why scoring is done deterministically rather
than by the model, how manual/patient-data-only criteria are handled, etc.).

## Files

- `hht_vcep_rules.md` — the HHT VCEP rules document fed to the model as
  context. Adapted from `data/classification_guidelines.py` (the same source of truth the real
  pipeline uses) but rewritten for a bare LLM with no tool access.
- `run_baseline.py` — the runner script.
- `outputs/` — where results land (gitignored contents recommended; the folder
  itself is created automatically on first run).

## Setup

```bash
cd AI-Agents-for-Scientific-Research
pip install -r requirements.txt   # langchain + langchain-google-genai should already be listed
cp .env.example .env              # if you haven't already
# edit .env: set GOOGLE_CLOUD_API_KEY to your Vertex-enabled Cloud Console key
```

This script only uses `GOOGLE_CLOUD_API_KEY` routed through Vertex AI (`vertexai=True`).
It will raise an error rather
than silently falling back to `GOOGLE_AI_STUDIO_API_KEY` (the free-tier key), keeping
all baseline usage billed to the same Vertex project as the pipeline.

## Run

```bash
# Quick smoke test on 3 variants, 1 pass, before committing to the full run
venv/bin/python -m baseline.run_baseline --limit 3 --passes 1

# Full run: all 200 variants, 3 passes each (600 model calls total)
venv/bin/python -m baseline.run_baseline --csv datasets/full_evaluation_dataset.csv --passes 3
```

Useful flags: `--model` (default `gemini-2.5-flash`), `--temperature` (default
0.4 — keep it above 0 or all passes will be identical), `--max-workers`
(default 4 — raise/lower depending on your rate limits), `--output` (default
`baseline/outputs/baseline_results.json`).

## Output

One JSON file with, per variant: every pass's raw model output, the
per-criterion applies/strength/evidence the model gave, the final
classification computed by the *same* `tools/scoring.py:classify()` your
pipeline uses, a majority-vote classification across passes, and (if present
in the input CSV) the gold-standard label for quick comparison.

To formally score this against gold-standard the same way pipeline runs are
scored, feed `baseline/outputs/baseline_results.json` into (or adapt)
`evaluation/evaluate_variant_classifications.py` alongside your usual gold-standard CSV.

## Known limitations to note in your methodology

- Knowledge cutoff: the model can't know about variants reported, or ClinVar
  entries updated, after its training cutoff.
- Possible memorization: if a variant's classification is well-known/public,
  the model might recall the answer rather than reason to it — check whether
  its per-criterion evidence is specific and plausible, or generic/hand-wavy.
- The model is instructed not to fabricate exact numeric values it doesn't
  know, and to mark those criteria as unable-to-determine instead — but this
  relies on the model following that instruction faithfully rather than a hard
  guarantee.
