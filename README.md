# AI Agents for Scientific Research

This repository implements a multi-agent pipeline for ACMG/AMP germline variant classification. It currently has detailed ClinGen HHT Variant Curation Expert Panel (VCEP) guidance for `ACVRL1` and `ENG`, plus a generic ACMG/AMP path for diseases without a configured VCEP specification.

Given a variant such as `NM_000020.3:c.557G>T` and a disease context, the pipeline gathers evidence from public genomics resources, evaluates applicable criteria, and returns a final classification: Benign, Likely Benign, Variant of Uncertain Significance (VUS), Likely Pathogenic, or Pathogenic.

The repository also includes a browser interface, a zero-tool LLM baseline, evaluation scripts, curated datasets, and retained JSON results.

## Pipeline design

```text
Variant + disease
      |
      v
VEP annotation and gene/variant-type detection
      |
      v
Plan agent selects and phases applicable criteria
      |
      v
Task -> Debug/retry -> Judge -> Check   (criteria run in parallel within each phase)
      |
      v
Deterministic ACMG/VCEP combining rules
      |
      +--> JSON result in outputs/
      +--> editable state in the browser GUI
```

The principal components are:

- `agents/plan_agent.py` creates criterion tasks and execution phases.
- `agents/task_agent.py` selects evidence tools and interprets their results.
- `agents/debug_agent.py` retries technical failures.
- `agents/judge_agent.py` checks the reasoning and criterion strength.
- `agents/check_agent.py` validates the final structured response.
- `tools/scoring.py` applies deterministic combining rules; the LLM does not choose the final class directly.
- `data/classification_guidelines.py` is the active guideline registry used by the pipeline, scorer, baseline, and GUI. It contains `HHT_CRITERIA_DB`, `ACMG_CRITERIA_DB`, exclusions, gene metadata, dependencies, and scoring rules.
- `data/hht_vcep_reference.py` is a source-traceable HHT CSpec reference without pipeline-specific operational guidance. It is not imported by the runtime.

The active data module is a rule and metadata registry, not a retrieval-augmented generation (RAG) system.

## Repository layout

```text
pipeline.py                         CLI and LangGraph orchestration
config.py                           Model/provider selection and rate limits
requirements.txt                    Direct runtime dependencies only
agents/                             Plan, task, debug, judge, check, and LLM code
tools/                              VEP, gnomAD, ClinVar, PubMed, LOVD, ERepo,
                                    computational, functional-evidence, and scoring tools
data/
  classification_guidelines.py      Active HHT and generic ACMG guideline registry
  hht_vcep_reference.py             Strict, source-traceable HHT reference
datasets/                           Gold-standard datasets and batch input CSVs
evaluation/
  evaluate_criterion_decisions.py   Research question 1: criterion-level metrics
  evaluate_variant_classifications.py
                                    Research question 2: final-class metrics
  run_agent_ablation.py             Research question 3: agent ablation runner
  merge_ablation_results.py         Merge independently run ablation modes
  evaluate_evidence_retrieval.py    Research question 4 metric specification (placeholder)
  outputs/                          Only the newest retained RQ1, RQ2, and RQ3 results
outputs/                            Pipeline results; separate from evaluation/outputs/
baseline/                           Zero-tool Gemini baseline and evaluator
gui/                                Browser GUI and HTTP API
presentations/                      Project presentation asset
```

`test_suite/`, `case_studies/`, and `notes/` were intentionally removed during the August 2026 repository cleanup.

## Setup

Python 3.12 is the supported environment for the current dependency set.

```bash
python3.12 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and add the key for the provider selected in `config.py`:

- `OPENAI_API_KEY` for the current default OpenAI configuration.
- `GOOGLE_CLOUD_API_KEY` for Vertex AI / Gemini and the baseline runner.
- `GOOGLE_AI_STUDIO_API_KEY` only for an AI Studio configuration you add explicitly.
- `ZAI_API_KEY` for the OpenAI-compatible z.ai endpoint.
- Ollama uses `OLLAMA_BASE_URL` from `config.py` and does not require an API key by default.

Do not commit `.env`; it is ignored by Git. `.env.example` contains placeholders only.

`requirements.txt` lists direct dependencies rather than the output of `pip freeze`. For example, `langchain-openai` installs the OpenAI SDK, `langchain-google-genai` installs the Google SDK, `metapub` installs its parsing stack, and scikit-learn installs SciPy. Those transitive packages should not be added manually unless the project begins importing them directly.

## Run the classifier

Classify one variant:

```bash
python -m pipeline \
  --variant "NM_000020.3:c.557G>T" \
  --disease "HHT"
```

The result is written to:

```text
outputs/<safe-variant>_<disease>_<timestamp>.json
```

Run a batch:

```bash
python -m pipeline --csv datasets/hht-batches.csv
```

By default, the CSV variant column is `hgvs_cdna` and the disease column is `condition`. Override them with `--variant-col` and `--disease-col`. If a row has no disease value, supply a fallback with `--disease`.

Each batch creates `outputs/batch_<timestamp>/` containing:

- one `<safe-variant>_<disease>.json` per successful variant;
- one `.error.json` per whole-variant failure; and
- `batch_summary.json`, written incrementally so interrupted runs retain their progress.

Resume a batch by passing the existing directory:

```bash
python -m pipeline \
  --csv datasets/full_evaluation_dataset.csv \
  --output-dir outputs/batch_<timestamp>
```

Existing successful per-variant files are skipped. Criterion-level errors can still appear inside an otherwise valid result and are preserved for evaluation.

## Browser GUI

Start the local browser interface from the repository root:

```bash
python -m gui.server
```

Open <http://127.0.0.1:8000>. The GUI can load cached JSON from `outputs/` or execute a live pipeline run. Users can edit criterion decisions and strengths, and the interface recalculates the classification with the same `tools.scoring.classify()` function used by the CLI.

See `gui/README.md` for the HTTP endpoints and criterion groups.

## Evaluation

The evaluation filenames describe their purpose while retaining the original research-question mapping:

| Research question | Script | Measures |
|---|---|---|
| RQ1 | `evaluation/evaluate_criterion_decisions.py` | Binary applies/does-not-apply accuracy, precision, recall, and F1 for each `(variant, criterion)` pair |
| RQ2 | `evaluation/evaluate_variant_classifications.py` | Five-class final variant accuracy, macro precision, macro recall, macro F1, and confusion matrix |
| RQ3 | `evaluation/run_agent_ablation.py` | Contribution of Debug and Judge agents across `full`, `no_debug`, `no_judge`, and `task_only` modes |
| RQ4 | `evaluation/evaluate_evidence_retrieval.py` | Planned precision, recall, Recall@k, and top-k retrieval accuracy; implementation is still pending |

### Criterion-decision evaluation (RQ1)

This evaluator reads detailed per-variant JSON files from the directory containing the supplied `batch_summary.json`. Gold labels come from `gt_criteria_applied` and `gt_criteria_not_met`.

```bash
python -m evaluation.evaluate_criterion_decisions \
  --gold_answer_csv_filename datasets/applied_only_evaluation_dataset.csv \
  --model_output_json_filename outputs/batch_20260729_194939/batch_summary.json \
  --output_dir evaluation/outputs
```

New files are named `<timestamp>_criterion_decisions.json`.

### Variant-classification evaluation (RQ2)

```bash
python -m evaluation.evaluate_variant_classifications \
  --gold_answer_csv_filename datasets/applied_only_evaluation_dataset.csv \
  --model_output_json_filename outputs/batch_20260729_194939/batch_summary.json \
  --output_dir evaluation/outputs
```

New files are named `<timestamp>_variant_classifications.json`.

### Agent ablation (RQ3)

Running all four modes performs live model and evidence-tool calls and can be expensive:

```bash
python -m evaluation.run_agent_ablation \
  --gold_answer_csv_filename datasets/hht_script_2.csv \
  --output_dir evaluation/outputs
```

Use `--mode full`, `--mode no_debug`, `--mode no_judge`, or `--mode task_only` with a shared `--run_id` to run modes separately. Merge them afterward:

```bash
python -m evaluation.merge_ablation_results \
  --run_id YOUR_SHARED_RUN_ID \
  --output_dir evaluation/outputs
```

### Retained evaluation results

`evaluation/outputs/` intentionally has exactly two JSON files and one ablation directory:

| Artifact | Contents |
|---|---|
| `20260729_221839_criterion_decisions.json` | Latest RQ1 result: 463 scored decisions, accuracy `0.8747`, F1 `0.7212`, 14 criterion errors, and one whole-variant error |
| `20260729_221858_variant_classifications.json` | Latest RQ2 result: 47 evaluated variants plus one failed variant, accuracy `0.3617`, macro F1 `0.3704` |
| `agent_ablation_20260731_132627/` | Latest RQ3 run, including raw predictions, summaries, per-mode batch results, and per-mode RQ1 metrics |

The retained RQ1 and RQ2 summaries were produced from `outputs/batch_20260729_194939/batch_summary.json`. That mixed-success batch is preserved intact because removing its single `.error.json` would change the reported failure counts.

## Output retention policy

`outputs/` and `evaluation/outputs/` serve different purposes:

- `outputs/` stores raw per-variant and batch pipeline runs used by the GUI and evaluators.
- `evaluation/outputs/` stores aggregate research metrics and ablation results.

The repository cleanup removed empty batches, failed-only batches, interrupted batches with no summary, debug/trial runs, the accidental `outputs/outputs/` directory, and standalone JSON files with no final classification/scoring or an empty `results` list. Successful batches and mixed batches with usable classifications remain. Do not treat a criterion-level error inside a classified result as a whole-pipeline failure; evaluators count those errors separately.

One inconsistent legacy batch summary reported only failure even though two valid, unreferenced classifications existed beside it. Those classifications were salvaged to `outputs/recovered_20260702_131103/`; the failed summary and error artifacts were discarded.

## Datasets

- `datasets/full_evaluation_dataset.csv` — full gold-standard evaluation set.
- `datasets/applied_only_evaluation_dataset.csv` — subset used by the newest retained RQ1/RQ2 run.
- `datasets/hht_script_2.csv` and `datasets/hht_script_testing_q2.csv` — historical HHT evaluation sets.
- `datasets/hht-batches.csv` — small batch input example.

Evaluation CSVs use `hgvs_cdna` for the variant, `condition` for the disease, `gt_classification` / `gt_classification_short` for final labels, and semicolon-separated `gt_criteria_applied` / `gt_criteria_not_met` fields for criterion-level gold labels.

## Verification without live API calls

These commands validate local structure and imports without running the costly pipeline:

```bash
python -m compileall agents baseline data evaluation gui tools pipeline.py config.py
python -m pipeline --help
python -m evaluation.evaluate_criterion_decisions --help
python -m evaluation.evaluate_variant_classifications --help
python -m evaluation.run_agent_ablation --help
```

Live classifications additionally require provider credentials and network access to the configured LLM and genomics services.
