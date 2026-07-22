"""
Zero-tool LLM baseline for HHT variant classification.

Purpose
-------
The pipeline (pipeline.py) classifies variants using a tool-augmented,
multi-agent LangGraph architecture that gathers real evidence (gnomAD, VEP,
ClinVar, PubMed, LOVD, etc.) before reasoning over it. This script answers a
different question: how well can the *same underlying model family* do if it
only uses its own parametric knowledge, with no tool calls and no web search?

This is a "closed-book" baseline, run against the same variant list and the
same combining rules (imported directly from data/planrag.py and scored with
the same tools/scoring.py classify() function your pipeline uses), so results
are directly comparable.

Design choices worth knowing about (see conversation / methodology notes):
  - Uses Gemini (google_genai), not Claude, specifically because your
    pipeline's agents already run on Gemini. Using the same base model
    isolates the effect of the agentic/tool-calling architecture from any
    difference in underlying model capability -- a cleaner ablation than
    comparing against a different model family.
  - No tools/functions are attached to the model call, so it cannot look
    anything up -- it must answer from its own weights.
  - The model outputs per-criterion applies/strength/evidence, and this
    script -- not the model -- runs the deterministic classify() combining
    logic. This keeps the comparison focused on evidence *reasoning* rather
    than on whether the model can also correctly re-derive the ACMG/AMP
    combining math.
  - Manual-input criteria (PP4_Moderate, PP1, BS4, BP2, BP5 -- anything
    flagged `deferred: True` in planrag.py) require real patient/family data
    the model can't have, so they're always excluded from scoring here,
    matching how your pipeline treats them absent patient data.
  - Runs each variant multiple times (--passes, default 3) at nonzero
    temperature to capture run-to-run variance, since a single LLM run is
    not a reliable estimate of "what the model would say."

Usage
-----
    cd AI-Agents-for-Scientific-Research
    pip install langchain langchain-google-genai python-dotenv  # if not already installed
    cp .env.example .env   # make sure GOOGLE_API_KEY (billed Vertex AI key) is set
    venv/bin/python -m baseline.run_baseline --csv datasets/full_evaluation_dataset.csv --passes 3

Useful flags:
    --limit N          only run the first N variants (for a quick smoke test)
    --model NAME        Gemini model name (default: gemini-2.5-flash)
    --temperature F      sampling temperature (default: 0.4 -- must be > 0 for
                        multiple passes to actually differ)
    --max-workers N      how many variants to process concurrently (default: 4;
                        keep this low for free-tier API rate limits)
    --output PATH        where to write the single aggregated JSON result file

Output
------
One JSON file (default: baseline/outputs/baseline_results.json) containing,
for every variant and every pass: the raw per-criterion model output, the
classify() result (final call + rule matched + bucket counts), and -- if the
input CSV has a gt_classification_short column -- the gold-standard label for
quick eyeballing. A per-variant majority-vote classification across passes is
also included.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
import traceback
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# Make the repo root importable when this script is run as `python -m baseline.run_baseline`
# or `python baseline/run_baseline.py` from the repo root.
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO_ROOT / ".env", override=True)

from data.planrag import PLANRAG_DB, EXCLUDED_CRITERIA  # noqa: E402
from tools.scoring import classify  # noqa: E402

BASELINE_DIR = Path(__file__).resolve().parent
RULES_PATH = BASELINE_DIR / "hht_vcep_rules.md"
DEFAULT_CSV = REPO_ROOT / "datasets" / "full_evaluation_dataset.csv"
DEFAULT_OUTPUT = BASELINE_DIR / "outputs" / "baseline_results.json"

# Criteria the model should evaluate. Anything marked deferred:True in planrag
# requires real patient/family data the model can't have, so we still ask
# about it (in case synthetic patient data is ever added to the CSV later)
# but treat "no data provided" as the default expectation.
CRITERIA_KEYS = [k for k in PLANRAG_DB.keys() if k != "SCORING"]
DEFERRED_CRITERIA = {k for k in CRITERIA_KEYS if PLANRAG_DB[k].get("deferred")}

VALID_PATHOGENIC_STRENGTHS = {"very_strong", "strong", "moderate", "supporting"}
VALID_BENIGN_STRENGTHS = {"benign_strong", "benign_supporting"}


# ──────────────────────────────────────────────────────────────────────────────
# Prompt construction
# ──────────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are acting as an expert ACMG/AMP germline variant curator, evaluating a
single variant against the ClinGen HHT (Hereditary Hemorrhagic Telangiectasia)
Variant Curation Expert Panel (VCEP) rules.

CRITICAL CONSTRAINTS:
- You have NO tools, NO web search, and NO ability to look anything up. You may
  only use knowledge already in your weights.
- Do NOT fabricate specific numbers (exact gnomAD allele counts/frequencies,
  exact REVEL/SpliceAI scores, exact proband counts, exact PMIDs) unless you are
  confident you actually know them for this specific variant. If you are not
  confident, say the value is unknown to you and mark the criterion as unable to
  determine (applies: null) rather than guessing.
- Clearly distinguish, in your evidence/reasoning text, between "I recall
  specific published evidence for this exact variant" and "I am inferring from
  general knowledge of this gene/region/variant type" -- these are very
  different confidence levels and should read differently.
- The five manual-input criteria (PP1, BS4, BP2, PP4_MODERATE, BP5) require real
  patient/family data you do not have. Unless patient data is explicitly given
  to you below, set applies to false and applied_strength to null for these,
  with evidence noting no patient data was provided.
- Do not apply any of the criteria listed as excluded/not-applicable for HHT.

You will be given the full HHT VCEP rules document, then a specific variant.
Evaluate every non-excluded criterion and return ONLY a single JSON object,
wrapped in a ```json code fence, with this exact shape:

```json
{
  "CRITERION_KEY": {
    "applies": true | false | null,
    "applied_strength": "very_strong" | "strong" | "moderate" | "supporting" |
                          "benign_stand_alone" | "benign_strong" | "benign_supporting" | null,
    "evidence": "short reasoning / evidence statement, noting confidence level"
  },
  ...
}
```

Include an entry for every criterion key listed in the rules document's
"Automatable criteria" and "Manual-input criteria" sections (use the exact
criterion keys as given, e.g. PM2_SUPPORTING, BA1, BS1, PS4, PM1, PVS1, PM5,
PS3, PS1, PP3, PM4, BP4, BP7, PP1, BS3, BS4, BP2, BP5_MODERATE-style names as
applicable). Do not include the excluded criteria. Do not include any text
outside the single JSON code fence -- no preamble, no final classification (a
separate deterministic step will compute the final classification from your
per-criterion outputs)."""


def build_rules_text() -> str:
    return RULES_PATH.read_text(encoding="utf-8")


def build_user_prompt(rules_text: str, gene: str, hgvs_cdna: str, variant_type: str | None) -> str:
    criteria_list = ", ".join(CRITERIA_KEYS)
    variant_desc = f"Gene: {gene}\nVariant (HGVS cDNA): {hgvs_cdna}"
    if variant_type:
        variant_desc += f"\nKnown variant type (if provided): {variant_type}"
    return f"""{rules_text}

---

## Variant to classify

{variant_desc}

Evaluate each of the following criterion keys and return the JSON object
described in the system instructions: {criteria_list}
"""


# ──────────────────────────────────────────────────────────────────────────────
# Model call
# ──────────────────────────────────────────────────────────────────────────────

def get_llm(model: str, temperature: float):
    """
    Builds a LangChain Gemini chat model with NO tools attached (so it has no
    way to search/browse), routed through the billed Vertex AI backend using
    GOOGLE_API_KEY -- the billed Cloud Console key set in this repo's .env
    (note: agents/llm/llm.py's create_llm() reads GOOGLE_CLOUD_API_KEY instead;
    this repo's actual .env only defines GOOGLE_API_KEY for the Vertex-billed
    key, so this script matches the .env that's actually in use rather than
    that other module's variable name). This script deliberately does NOT fall
    back to GOOGLE_AI_STUDIO_API_KEY (the free-tier key): all baseline calls
    should be billed to the same Vertex project the pipeline itself uses, so
    usage/cost accounting stays in one place and isn't split across two
    different Google accounts/quotas.
    """
    from langchain.chat_models import init_chat_model

    cloud_key = os.getenv("GOOGLE_API_KEY")
    if not cloud_key or cloud_key == "your_google_cloud_api_key_here":
        raise RuntimeError(
            "GOOGLE_API_KEY is not set in your .env file. This script only "
            "uses the billed Vertex AI key (not GOOGLE_AI_STUDIO_API_KEY) -- "
            "set GOOGLE_API_KEY to your Vertex-enabled Cloud Console key."
        )

    return init_chat_model(
        model=model,
        model_provider="google_genai",
        api_key=cloud_key,
        vertexai=True,
        temperature=temperature,
        # Without an explicit timeout, a bad/missing credential can make the
        # underlying google-auth client silently fall back to Application
        # Default Credentials and block for a long time trying to reach the
        # GCP metadata server (which doesn't exist outside GCP infra) -- that
        # looks exactly like the whole script "hanging" with no error. Capping
        # the request means a bad key fails fast instead.
        timeout=60,
        max_retries=2,
    )


JSON_FENCE_RE = re.compile(r"```json\s*(.*?)\s*```", re.DOTALL)


def content_to_text(content) -> str:
    """
    Normalizes a LangChain message's `.content` into a plain string.

    ChatGoogleGenerativeAI (and other providers) don't always return a plain
    string here -- for some Gemini responses `.content` is a list of content
    blocks instead, e.g. [{"type": "text", "text": "..."}] or a mix of str and
    dict entries. Join everything text-like into one string so downstream
    parsing doesn't have to care about the shape.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                # Common shapes: {"type": "text", "text": "..."} or {"text": "..."}
                parts.append(item.get("text", "") or "")
            else:
                parts.append(str(item))
        return "".join(parts)
    return str(content)


def extract_json(raw_text: str) -> dict:
    """Pulls the JSON object out of a ```json ... ``` fence, with a couple of fallbacks."""
    match = JSON_FENCE_RE.search(raw_text)
    candidate = match.group(1) if match else raw_text.strip()
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        # Fallback: find the first '{' and last '}' and try again.
        start, end = candidate.find("{"), candidate.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(candidate[start : end + 1])
        raise


def sanitize_criteria_output(raw: dict) -> dict:
    """
    Coerces the model's raw per-criterion dict into the shape classify()
    expects, dropping/ignoring anything unrecognised and defaulting missing
    criteria to "not evaluated by model".
    """
    cleaned = {}
    for key in CRITERIA_KEYS:
        entry = raw.get(key) or {}
        applies = entry.get("applies")
        strength = entry.get("applied_strength")
        evidence = entry.get("evidence", "")

        if key in DEFERRED_CRITERIA and applies is not True:
            applies = False  # no patient data -> never counts toward scoring

        if strength is not None and strength not in (
            VALID_PATHOGENIC_STRENGTHS | VALID_BENIGN_STRENGTHS
        ):
            strength = None  # ignore malformed/hallucinated strength labels

        cleaned[key] = {
            "applies": applies if isinstance(applies, bool) else False,
            "applied_strength": strength,
            "status": "ok" if key in raw else "not_returned_by_model",
            "evidence": evidence,
        }
    return cleaned


def run_single_pass(llm, rules_text: str, gene: str, hgvs_cdna: str, variant_type: str | None, pass_index: int) -> dict:
    prompt = build_user_prompt(rules_text, gene, hgvs_cdna, variant_type)
    response = llm.invoke(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
    )
    raw_content = response.content if hasattr(response, "content") else response
    raw_text = content_to_text(raw_content)
    raw_json = extract_json(raw_text)
    per_criterion = sanitize_criteria_output(raw_json)
    scored = classify(per_criterion, disease="HHT")
    return {
        "pass": pass_index,
        "raw_model_output": raw_text,
        "per_criterion": per_criterion,
        "classification_result": scored,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Variant-level orchestration
# ──────────────────────────────────────────────────────────────────────────────

def process_variant(row: dict, model: str, temperature: float, passes: int, rules_text: str) -> dict:
    gene = row.get("gene", "")
    hgvs_cdna = row.get("hgvs_cdna", "")
    variant_type = row.get("variant_type") or None
    variation_id = row.get("variation_id", "")

    result = {
        "variation_id": variation_id,
        "gene": gene,
        "hgvs_cdna": hgvs_cdna,
        "gold_standard": {
            "gt_classification": row.get("gt_classification"),
            "gt_classification_short": row.get("gt_classification_short"),
            "gt_criteria_applied": row.get("gt_criteria_applied"),
        },
        "passes": [],
        "error": None,
    }

    llm = get_llm(model, temperature)

    for i in range(1, passes + 1):
        for attempt in range(3):
            try:
                pass_result = run_single_pass(llm, rules_text, gene, hgvs_cdna, variant_type, i)
                result["passes"].append(pass_result)
                break
            except Exception as exc:  # noqa: BLE001
                if attempt == 2:
                    result["passes"].append(
                        {
                            "pass": i,
                            "error": f"{type(exc).__name__}: {exc}",
                            "traceback": traceback.format_exc(),
                        }
                    )
                else:
                    time.sleep(2 * (attempt + 1))

    final_calls = [
        p["classification_result"]["classification"]
        for p in result["passes"]
        if "classification_result" in p
    ]
    if final_calls:
        vote_counts = Counter(final_calls)
        result["majority_classification"] = vote_counts.most_common(1)[0][0]
        result["vote_counts"] = dict(vote_counts)
    else:
        result["majority_classification"] = None
        result["vote_counts"] = {}

    # Top-level error status: None if every pass succeeded, otherwise a
    # summary of which pass(es) failed and why. A variant can partially
    # succeed (e.g. pass 2 of 3 failed after retries) -- this surfaces that
    # instead of silently only reporting via the per-pass "error" keys.
    failed_passes = [p for p in result["passes"] if "error" in p]
    if failed_passes:
        result["error"] = "; ".join(
            f"pass {p.get('pass')}: {p['error']}" for p in failed_passes
        )
    else:
        result["error"] = None

    return result


def load_variants(csv_path: Path, limit: int | None) -> list[dict]:
    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if limit:
        rows = rows[:limit]
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV, help="Variant CSV (default: datasets/full_evaluation_dataset.csv)")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output JSON path")
    parser.add_argument("--model", default="gemini-3.5-flash", help="Gemini model name")
    parser.add_argument("--temperature", type=float, default=0.4, help="Sampling temperature (keep > 0 for multiple passes to vary)")
    parser.add_argument("--passes", type=int, default=3, help="Number of independent passes per variant")
    parser.add_argument("--max-workers", type=int, default=4, help="Concurrent variants in flight (keep low for free-tier rate limits)")
    parser.add_argument("--limit", type=int, default=None, help="Only process the first N variants (smoke test)")
    args = parser.parse_args()

    rules_text = build_rules_text()
    variants = load_variants(args.csv, args.limit)
    print(f"Loaded {len(variants)} variants from {args.csv}")
    print(f"Model: {args.model} | temperature: {args.temperature} | passes: {args.passes} | workers: {args.max_workers}")

    args.output.parent.mkdir(parents=True, exist_ok=True)

    meta = {
        "model": args.model,
        "temperature": args.temperature,
        "passes": args.passes,
        "csv_source": str(args.csv),
        "num_variants": len(variants),
        "criteria_evaluated": CRITERIA_KEYS,
        "deferred_criteria_no_patient_data": sorted(DEFERRED_CRITERIA),
        "excluded_criteria": EXCLUDED_CRITERIA,
    }

    def write_output(results: list[dict]) -> None:
        # Rewrites the whole output file on every call. For ~200 variants this
        # is cheap enough to do after every single variant finishes, so the
        # file on disk always reflects current progress -- you can open/tail
        # it mid-run instead of waiting for the entire batch to complete, and
        # a crash partway through still leaves a valid, usable partial file.
        payload = {"meta": {**meta, "num_variants_completed": len(results)}, "results": results}
        tmp_path = args.output.with_suffix(args.output.suffix + ".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        tmp_path.replace(args.output)  # atomic on POSIX -- avoids a reader seeing a half-written file

    all_results = []
    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        futures = {
            executor.submit(process_variant, row, args.model, args.temperature, args.passes, rules_text): row
            for row in variants
        }
        done = 0
        for future in as_completed(futures):
            row = futures[future]
            done += 1
            try:
                all_results.append(future.result())
            except Exception as exc:  # noqa: BLE001
                error_message = f"{type(exc).__name__}: {exc}"
                all_results.append(
                    {
                        "variation_id": row.get("variation_id"),
                        "gene": row.get("gene"),
                        "hgvs_cdna": row.get("hgvs_cdna"),
                        "gold_standard": {
                            "gt_classification": row.get("gt_classification"),
                            "gt_classification_short": row.get("gt_classification_short"),
                            "gt_criteria_applied": row.get("gt_criteria_applied"),
                        },
                        "passes": [],
                        "majority_classification": None,
                        "vote_counts": {},
                        "error": error_message,
                    }
                )

            last_result = all_results[-1]
            status = "None" if last_result.get("error") is None else last_result["error"]
            print(f"  [{done}/{len(variants)}] done: {row.get('hgvs_cdna')} | error: {status}")

            write_output(all_results)  # live update after every variant

    print(f"\nWrote aggregated results for {len(all_results)} variants to {args.output}")


if __name__ == "__main__":
    main()
