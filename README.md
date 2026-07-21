# AI Agents for Scientific Research: Automated ACMG/AMP Variant Classification

A multi-agent LLM pipeline that automates ACMG/AMP germline variant classification, starting with the ClinGen HHT (Hereditary Hemorrhagic Telangiectasia) Variant Curation Expert Panel (VCEP) specification for *ACVRL1* and *ENG*, and extensible to the general ACMG framework for other genes.

Given a variant (e.g. `NM_000020.3:c.557G>T`) and a disease context, the pipeline evaluates each applicable ACMG/AMP criterion by gathering evidence from public genomics resources (Ensembl VEP, gnomAD, ClinVar, PubMed, LOVD), reasoning over that evidence with an LLM agent per criterion, and combining the results into a final classification — Pathogenic, Likely Pathogenic, VUS, Likely Benign, or Benign — using the same combining rules a human curator would apply.

A browser GUI sits on top of the pipeline for human-in-the-loop review: every criterion is shown as an editable checkbox pre-populated from a pipeline run, and the classification recalculates live as a reviewer overrides individual calls. The GUI can be found on the following huggingface space, without needing to clone the code: https://huggingface.co/spaces/ashkankhilwatgar1/Variant-interpretation-UI

## Why this exists

Manual ACMG/AMP variant curation is slow and requires specialist expertise, which limits how many variants of uncertain significance can be reviewed and creates a backlog relevant to clinical diagnosis (HHT in particular is under-curated relative to how many carriers exist). This project explores whether an LLM agent pipeline can reliably automate the evidence-gathering and reasoning steps of curation, while keeping a human reviewer in the loop for final sign-off rather than fully automating away expert judgment.

## How it works

The pipeline is a directed multi-agent graph (built with LangGraph), not a single LLM call:

- **Plan agent** — determines which ACMG/AMP criteria are applicable to the given variant and disease context (filtering out criteria excluded by the relevant VCEP, or not applicable to the variant's type), and dispatches one task per criterion.
- **Task agent(s)** — run in parallel, one per criterion, each gathering the specific evidence that criterion requires (e.g. population frequency from gnomAD for BA1/BS1/PM2, computational predictions from REVEL/SpliceAI for PP3/BP4, functional study evidence pulled from PubMed abstracts for PS3/BS3, prior classifications from ClinVar/LOVD for PS1/PM5/PS4) and reasoning over it to decide whether the criterion applies.
- **Debug agent** — catches and retries failed tool calls or malformed intermediate output.
- **Judge / check agents** — validate individual criterion calls before they're combined into a final classification.
- **Scoring** (`tools/scoring.py`, rules defined in `data/planrag.py`) — combines all applied criteria using the ACMG/AMP point system (fixed- and variable-strength criteria, incompatible-combination downgrades like PM1+PM5, and the standard precedence order: Benign → Likely Benign → Pathogenic → Likely Pathogenic → VUS) to produce the final call, with the matching rule shown for transparency.

Criterion metadata — which criteria are automatable, which need manual patient-specific input, which are excluded entirely by the HHT VCEP (with the cited exclusion reason), and the exact scoring/combining rules — all live in `data/planrag.py` as a single source of truth used by both the CLI pipeline and the GUI, so the two never disagree on the rules.

## Project structure

```
pipeline.py          Main entrypoint — orchestrates the LangGraph pipeline end-to-end
agents/               plan / task / debug / judge / check agents, LLM wrapper
tools/                Evidence-gathering tools: vep.py, gnomad.py, clinvar.py, pubmed.py,
                      lovd.py, computational.py, functional_evidence.py, scoring.py
data/                 planrag.py — criteria metadata, exclusion reasons, scoring rules
                      (single source of truth for both the pipeline and GUI)
gui/                  Browser demo — server.py backend + static/ frontend
                      (see gui/README.md for the demo's own documentation)
evaluation/           question1-4.py — scripts for the evaluation questions posed by
                      our faculty advisor, scored against hand-labeled gold-standard CSVs
datasets/             Gold-standard evaluation CSVs and batch input lists
outputs/              Cached per-variant pipeline run results (JSON), used for both
                      evaluation and as pre-populated data in the GUI
case_studies/         Dated working notes/results from specific variant deep-dives
notes/                daily-notes.md — running project log across contributors
config.py             Model provider/name configuration (Gemini via Vertex AI by default;
                      OpenAI, Ollama, and z.ai/GLM also supported) and API key loading
```

## Quick start

Requires Python 3.10+ (recommended: 3.12; verified on 3.11–3.13).

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# edit .env with your own API keys (Vertex AI / Gemini by default — see config.py)

# 3. Classify a single variant
python -m pipeline --variant "NM_000020.3:c.557G>T" --disease "HHT"

# 4. Run a batch of variants from a CSV
python -m pipeline --csv datasets/hht-batches.csv
```

### Run the browser GUI (not from huggingface)

```bash
venv/bin/python -m gui.server
```

Then open `http://127.0.0.1:8000`. The GUI can either pre-populate from a cached pipeline run (instant) or trigger a live pipeline run for a new variant (slow — real LLM + external API calls). See `gui/README.md` for the full HTTP API and criterion-group breakdown.

### Run an evaluation

```bash
python -m evaluation.question2 \
  --gold_answer_csv_filename datasets/hht_script_2.csv \
  --model_output_json_filename outputs/batch_20260707_125513/batch_summary.json \
  --output_dir evaluation/outputs
```

## Disease scope

The pipeline currently ships with a full criteria specification for **HHT** (genes *ACVRL1*/*ENG*), following the published ClinGen HHT VCEP rules — including which of the 28 standard ACMG/AMP criteria are excluded outright for HHT (e.g. PS2/PM3/PM6, which assume inheritance patterns that don't hold for this autosomal-dominant, low-de-novo-rate disease) and which are adapted with disease-specific strength or evidence thresholds. A more general ACMG criteria set (not tied to a specific VCEP) is also supported for genes/diseases without a published VCEP specification, for broader applicability beyond HHT.

## Team

Ashkan, Simon, and Suning, working under faculty guidance on this research project, with ongoing evaluation against hand-labeled gold-standard variant classifications to validate pipeline accuracy against expert human curation.

## Status

Actively developed. See `notes/daily-notes.md` for a running log of implementation decisions, known issues, and day-to-day progress across contributors. A research poster and paper (methodology and introduction currently in progress) are being prepared to present these results.
