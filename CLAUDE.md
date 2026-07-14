# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A LangGraph-based multi-agent pipeline that classifies genetic variants (ACMG/AMP and HHT-VCEP criteria) for pathogenicity, using LLMs to reason over evidence pulled from ClinVar, gnomAD, Ensembl VEP, PubMed, LOVD, and other genomics APIs.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env   # then fill in real API keys
```

Requires Python 3.10+ (3.11–3.13 verified). API keys/config live in `.env` (loaded via `config.py`, which calls `load_dotenv(override=True)`).

## Common commands

```bash
# Single variant
python -m pipeline --variant "NM_000020.3:c.557G>T" --disease "HHT"

# Batch (CSV of variants)
python -m pipeline --csv hht-batches.csv

# Evaluation against a gold-standard dataset
python -m evaluation.question2 --gold_answer_csv_filename hht_script_2.csv --model_output_json_filename outputs/batch_.../batch_summary.json --output_dir evaluation/outputs

# Tests (pytest)
pytest test/test_vep.py
pytest test/test_functional_evidence.py -k some_test
```

There is no lint/format tooling configured in this repo.

## Architecture

### Pipeline flow (`pipeline.py`)

`run_pipeline(variant, disease)` is the entry point:

1. **Variant type detection** — `tools/vep.annotate_variant()` calls Ensembl VEP to get variant consequence/type and gene symbol. If VEP fails, falls back to NCBI transcript→gene lookup.
2. **Criteria selection** — `get_criteria_for_disease()` picks the criteria set: `HHT_CRITERIA` (a fixed VCEP list) if the disease is HHT/VCEP-covered (`data.planrag.is_vcep_disease`), otherwise the generic `ACMG_CRITERIA` from `data/planrag.py`. `filter_criteria_by_variant_type()` then drops criteria whose PlanRAG entry restricts `variant_types` and the detected type doesn't match (conservatively excludes when variant type is unknown).
3. **Plan agent** (`agents/plan_agent.run_plan`) — deterministically builds a phased task list from PlanRAG entries (no LLM call here). Tasks are grouped into up to 4 phases based on inter-criterion dependencies (e.g. PS4 needs PM2_SUPPORTING, PM5 needs PM1, PS3 needs PVS1 for splice exclusion).
4. **Parallel per-criterion execution** — a LangGraph `StateGraph` (`build_graph()`) fans out each phase's criteria via `Send`, runs each through `process_criterion()`, and fans back in at a barrier node before starting the next phase. This is the core reason phases exist: phase N+1 tasks can rely on phase N's `criterion_results`.
5. **Per-criterion agent chain** (`process_criterion()`) — for each criterion: checks `requires_applied`/`blocked_by` preconditions against prior results (skips if unmet), then runs **Debug → Judge → Check** agents in sequence:
   - `agents/debug_agent.run_debug` — internally runs the Task agent (`agents/task_agent.py`) to call genomics tools, catches technical/tool errors.
   - `agents/judge_agent.run_judge` — evaluates whether the criterion applies given the evidence; uses `CRITERION_GUARDRAILS`-style checks.
   - `agents/check_agent.run_check` — validates/normalizes the final output formatting.
6. **Scoring** — `tools/scoring.classify()` aggregates all criterion results into a final classification (Pathogenic/Likely Pathogenic/VUS/Likely Benign/Benign) using either HHT-VCEP or ACMG/AMP 2015 combining rules, bucketed by evidence strength (very strong/strong/moderate/supporting for pathogenic; stand-alone/strong/supporting for benign).

### PlanRAG (`data/planrag.py`, `data/strict_planrag.py`)

The knowledge base driving the whole pipeline. `GENE_DB` maps transcripts/genes to metadata (e.g. `cspec_id`, LoF mechanism notes) for VCEP genes (ACVRL1, ENG for HHT). `ACMG_PLANRAG_DB` and the HHT-specific entries define, per criterion: dependencies (`requires_applied`, `blocked_by`), applicable `variant_types`, whether it's `excluded`/`deferred` for a given disease, and detailed instructions the Task agent uses at evaluation time. `query(criterion, gene=, disease=)` is the main lookup used throughout the pipeline — it resolves gene-specific branches (currently only PM1 and PVS1 differ between ACVRL1/ENG).

### Agents (`agents/`)

- `plan_agent.py` — deterministic task construction from PlanRAG (see above).
- `task_agent.py` — largest agent; orchestrates tool calls (ClinVar, gnomAD, VEP, PubMed, LOVD, functional evidence, computational predictors) to gather evidence per criterion.
- `debug_agent.py` — wraps Task agent execution, surfaces tool/technical errors before reasoning.
- `judge_agent.py` — the reasoning step that decides whether a criterion applies (added `CRITERION_GUARDRAILS` dict + `last_complete_output` tracking).
- `check_agent.py` — final formatting/validation pass on judge output.
- `agents/llm/llm.py` — shared `invoke_llm(model, provider, human_messsage)` wrapper; enforces a **per-model** shared rate limiter (see `GEMINI_REQUESTS_PER_MINUTE` in `config.py`) across concurrent LangGraph branches.

### Tools (`tools/`)

Each file wraps one external data source or computation: `clinvar.py`, `gnomad.py`, `vep.py` (Ensembl), `pubmed.py`, `lovd.py`, `erepo.py`, `gene_info.py`, `computational.py`, `functional_evidence.py` (LLM-driven abstract reading for PS3/BS3 — inherently less deterministic than the other tools), `scoring.py` (final classification logic), `utils.py` (shared helpers, e.g. transcript→gene resolution).

`gnomad.py` and `vep.py` each implement a global cross-thread request throttle (`GNOMAD_REQUESTS_PER_MINUTE`, `ENSEMBL_REQUESTS_PER_MINUTE` in `config.py`) because batch mode runs many variants/criteria concurrently and these public APIs 429/500 under burst load.

### Config (`config.py`)

`MODELS` dict assigns a provider+model per agent role (`plan`, `task`, `debug`, `judge`, `check`, `functional_evidence`) — currently all Google Gemini via Vertex AI (`GOOGLE_GENAI_USE_VERTEXAI=True`, per project billing setup — not the AI Studio free tier). An Ollama-based config is kept commented out as an alternative for local/offline runs. Rate limit constants (`GEMINI_REQUESTS_PER_MINUTE`, `GNOMAD_REQUESTS_PER_MINUTE`, `ENSEMBL_REQUESTS_PER_MINUTE`) are tuned empirically — see inline comments before changing them, since the real ceilings (Vertex quota, public API limits) aren't otherwise visible from this codebase.

### Evaluation (`evaluation/`)

Scripts compare pipeline batch output (`outputs/batch_.../batch_summary.json`) against gold-standard CSVs (e.g. `hht_script_2.csv`, `applied_only_evaluation_dataset.csv`) to compute accuracy and analyze which criteria/classifications diverge from expert VCEP calls. `question1.py`–`question4.py` correspond to different analysis angles; `merge_ablation_results.py` combines results from ablation runs (e.g. testing all 200 variants across criterion-disabled variants).

### Case studies (`case_studies/`)

Dated investigations (e.g. `case_studies/jul_13/bs3_ps3_case_study.ipynb`) into specific failure modes found during evaluation — check `daily-notes.md` for the running log of what's been investigated and open issues before starting new debugging work in this area.

## Known sharp edges (from `daily-notes.md`)

- PS3/BS3 use an LLM to read paper abstracts for functional evidence — inherently less stable than the deterministic tools; treat failures here differently from tool/API failures.
- Tool result caching does not currently retry on a cached "error" result from an earlier phase — a fix for this was flagged as in-progress; check current state of `tool_results` caching in `pipeline.py`/`agents/debug_agent.py` before assuming errors are retried.
- Final classification logic has previously shown inconsistency where the same set of applied criteria produced different classifications — if touching `tools/scoring.py`, check against `evaluation/outputs` regression cases first.
