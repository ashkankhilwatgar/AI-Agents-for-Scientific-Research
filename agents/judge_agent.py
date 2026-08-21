import os
import requests
import json
from config import RETRY_LIMIT
from agents.task_agent import run_task
from data.classification_guidelines import query, get_gene_from_transcript
from .llm.llm import create_llm
from typing import Optional, TypeAlias, Any
from config import MODELS
ToolResults: TypeAlias = dict[str, dict[str, Any]]
from pydantic import BaseModel
from .llm.response_schema import CheckReasoningResult

# Opt-in retry-attempt logging. Off by default — set PIPELINE_DEBUG_LOG=1 to
# capture each retry attempt's check result/feedback/task_output to a local
# file for diagnosing retry-limit failures without guesswork.
_DEBUG_LOG_PATH = os.environ.get("PIPELINE_DEBUG_LOG")


def _log_attempt(agent: str, criterion: str, variant: str, attempt: int, result: dict, task_output: dict) -> None:
    if not _DEBUG_LOG_PATH:
        return
    try:
        with open(_DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "agent": agent,
                "criterion": criterion,
                "variant": variant,
                "attempt": attempt,
                "check_result": result,
                "task_output": task_output,
            }) + "\n")
    except Exception:
        pass


def call_judge_agent(prompt: str, output_schema: type[BaseModel]) -> BaseModel:
    """
    Invoke the task LLM and return its response as a structured Pydantic object.
    """
    llm = create_llm(
        model=MODELS["judge"]["model"],
        provider=MODELS["judge"]["provider"],
        temperature=0
    )
    structured_llm = llm.with_structured_output(output_schema)
    response = structured_llm.invoke([{"role": "user", "content": prompt}])
    return response


# ── Criterion-specific guardrails ─────────────────────────────────────────────
# Injected into every Judge prompt to prevent hallucinated rejection reasons.
# Each entry contains rules that are EXPLICITLY prohibited from being flagged.
CRITERION_GUARDRAILS = {
    "PS4": """
PS4 GUARDRAIL (HHT VCEP):
PS4 evidence source for HHT VCEP is PubMed case reports, ClinVar, ERepo, or LOVD.
The pipeline runs a ClinVar → ERepo → LOVD → PubMed fallback chain internally.
tool_used="clinvar" is always the correct value for PS4 regardless of which source provided the proband count.

Valid rejection reasons for PS4:
  1. Proband count was miscounted from the retrieved evidence
  2. PM2_Supporting precondition was not checked
  3. Duplicate patients were not excluded
  4. The applies field contradicts the proband count

DO NOT reject PS4 for any of the following:
  - Missing ERepo queries (already handled internally by the fallback chain)
  - Missing LOVD queries (already handled internally by the fallback chain)
  - tool_used being "clinvar" instead of "erepo" or "lovd" — do NOT ask the task agent to change tool_used
  - PubMed being the only source cited — this is valid when ERepo/LOVD/ClinVar returned no results
  - Evidence mentioning an alternate molecular basis or BP5 language — that is a separate criterion
If the Task agent found probands and counted them correctly, the output is CORRECT.
""",
    "PM2_SUPPORTING": """
PM2_SUPPORTING GUARDRAIL (HHT VCEP):
Threshold is <6 total alleles in gnomAD OR <0.00004 (0.004%) in any gnomAD subpopulation.
DO NOT apply the generic ACMG threshold of AF < 0.001 — that is wrong for HHT VCEP.
If variant is absent from gnomAD entirely, PM2_Supporting APPLIES (applies=true).
DO NOT flag as error if the Task agent correctly concludes PM2_Supporting applies for a rare/absent variant.
""",
    "BA1": """
BA1 GUARDRAIL (HHT VCEP):
BA1 applies ONLY when Popmax FAF >= 0.01 (1%).
A LOW frequency means BA1 does NOT apply — applies=false is the CORRECT result for rare variants.
DO NOT flag as error if the Task agent correctly concludes BA1 does not apply for a rare variant.
""",
    "BS1": """
BS1 GUARDRAIL (HHT VCEP):
BS1_Strong: Popmax FAF > 0.002 and < 0.01
BS1_Supporting: Popmax FAF > 0.0008 and <= 0.002
DO NOT use the generic ACMG BS1 threshold. Only flag if the threshold comparison itself is wrong.
""",
    "BP4": """
BP4 GUARDRAIL (HHT VCEP):
For missense variants: REVEL <= 0.15 AND SpliceAI <= 0.1 — BOTH required (AND logic, not OR).
For synonymous/intronic: SpliceAI <= 0.1 only.
DO NOT reject if the Task agent correctly applied AND logic for missense.
DO NOT require REVEL for synonymous/intronic variants.
""",
    "PP3": """
PP3 GUARDRAIL (HHT VCEP):
For missense variants: REVEL >= 0.644 OR SpliceAI >= 0.2 — OR logic, either one alone is sufficient.
For synonymous/intronic: SpliceAI >= 0.2 only.
DO NOT reject if the Task agent correctly applied OR logic for missense.
DO NOT require both REVEL and SpliceAI to both meet threshold for PP3 to apply.
""",
}


def check_reasoning(task_output: dict, guideline_entry: dict | None = None) -> dict:
    """
    Evaluates Task agent output for reasoning errors.
    Returns a pass/fail dict with feedback if failed.
    """
    criterion = task_output.get("criterion", "")

    guideline_context = ""
    if guideline_entry:
        guideline_context = f"""
The following classification rules apply to this criterion:
{json.dumps(guideline_entry, indent=2)}
Use these rules as the ground truth when evaluating whether the applies field is correct.
"""

    # inject criterion-specific guardrail if one exists
    guardrail = CRITERION_GUARDRAILS.get(criterion, "")
    guardrail_block = f"\nCRITERION-SPECIFIC RULES (these override general reasoning rules):\n{guardrail}" if guardrail else ""

    prompt = f"""You are a reasoning validator for a variant classification pipeline.
You are an expert bioinformatician with deep knowledge of ACMG variant classification criteria.

You will be given the output of a variant classification task. Your job is to check
for reasoning errors only — not technical issues.
{guideline_context}{guardrail_block}
Reasoning errors include:
- The wrong tool was used for the criterion being evaluated
  (e.g. using ClinVar instead of gnomAD for a population frequency criterion like PM2)
- The evidence retrieved does not actually address the criterion being evaluated
- The reasoning incorrectly maps the evidence to the criterion
  (e.g. concluding PP3 does not apply when the REVEL score meets the threshold)
- The applies field contradicts the evidence and reasoning

The following are NOT reasoning errors — do not flag these:
- PS4 evidence mentioning "alternate molecular basis", "alternate explanation", or BP5 language.
  The same patient can appear in both PS4 (proband count) and BP5 (alternate explanation) contexts.
  If the task agent found a proband count and correctly applied PS4, do not reject it on the grounds
  that the evidence also mentions an alternate molecular explanation — that is a separate criterion (BP5)
  and does not invalidate the PS4 finding.
- PS4 tool_used field showing "clinvar" even when the underlying evidence came from ERepo, LOVD, or PubMed.
  The "clinvar" tool internally runs a ClinVar → ERepo → LOVD → PubMed fallback chain for PS4.
  tool_used="clinvar" is always the correct value for PS4 regardless of which fallback source
  provided the proband count. Do NOT ask the task agent to change tool_used to "lovd" or "erepo". Doing so is BAD 
  and unacceptable.
- A criterion applying at a lower strength than the maximum possible (e.g. PS4_Supporting instead of PS4_Strong)
  is valid if the proband count supports it.
- CRITICAL — "applies" and "applied_strength" are two SEPARATE, INDEPENDENT fields:
  "applies" (bool) means the criterion fires at all. "applied_strength" (very_strong/strong/moderate/supporting)
  is the severity tier at which it fires. applies=true + applied_strength="moderate" is a FULLY CONSISTENT,
  CORRECT result — it means "this criterion applies, at moderate strength." This is NOT a contradiction.
  Do NOT flag this combination as an error. Do NOT reason that applies=true implies the strongest tier, and
  do NOT ask the task agent to flip applies to false just because the strength is sub-maximal. Only flag a
  real error here if the strength tier itself is wrong for the evidence (e.g. evidence supports 4+ probands
  but applied_strength is "supporting" instead of "strong") — verify the tier against the guideline thresholds
  before flagging, and if you flag it, give ONE specific corrected (applies, applied_strength) pair and do not
  reverse that verdict on a later attempt for the same evidence.
- Evidence showing a variant is absent from a database — absence is valid evidence.
- The task agent concluding BP1 does NOT apply because the gene causes disease via missense variants.
  BP1 requires that the gene causes disease PRIMARILY through truncating/LOF variants with missense
  rarely pathogenic. If the task agent determined that missense variants are a known pathogenic
  mechanism in the gene, BP1 not applying is the correct answer. Do NOT override this conclusion
  based on your own belief about the disease mechanism — the task agent's gene-specific reasoning
  must be respected. Only flag BP1 if the gnomAD gene constraint tool was not used at all, or if a
  threshold comparison is demonstrably wrong (e.g. pLI value misread).
- Similarly, the task agent concluding PP2 does NOT apply because mis_z is below threshold is correct
  when the gnomAD gene tool was used and the threshold comparison is accurate. Do not override PP2
  based on your own belief about whether missense variants are pathogenic in the gene.

Task output:
{json.dumps(task_output, indent=2)}

You should follow the output schema

Some important rules: 
- The past field is True when there are no reasoning errors, and False otherwise.
- The error_type field must explain why the pass_ field is True or False.
- If the output does not pass, the feedback field must contain guidance for the downstream task agent on how to fix the error.
"""
    result = call_judge_agent(prompt, CheckReasoningResult).model_dump()
    return result


def run_judge(task: dict, tool_result: ToolResults, task_output: dict, gene_symbol: str | None = None, retry_count: int = 0) -> tuple[dict, dict]:
    """
    Main entry point called by pipeline.py.
    Receives validated task output from Debug agent.
    Checks reasoning, retries Task agent only if reasoning error found.

    On retry limit exhaustion, returns the last complete output rather than
    nulling everything — preserving partial evidence is better than applies=None.

    gene_symbol should be the pipeline's VEP/NCBI-resolved gene (the same value
    passed into run_debug). get_gene_from_transcript() below is a transcript→
    GENE_DB lookup that is currently unpopulated (GENE_DB entries have no
    "transcripts" list) and always returns None — it is kept only as a
    secondary check in case GENE_DB is populated in the future, and must never
    be the sole source of gene resolution here.
    """
    criterion = task.get("criterion")
    variant = task.get("variant", "")

    gene = gene_symbol
    if not gene and variant.startswith("NM_") and ":" in variant:
        gene = get_gene_from_transcript(variant.split(":")[0])

    disease = task.get("disease")
    guideline_entry = query(criterion, gene=gene, disease=disease)

    tool_cache_update = {}

    # track best complete output across all attempts — used if retry limit is hit
    last_complete_output = None
    if task_output.get("status") == "complete" and task_output.get("applies") is not None:
        last_complete_output = task_output

    while retry_count < RETRY_LIMIT:
        result = check_reasoning(task_output, guideline_entry)
        _log_attempt("judge", criterion, variant, retry_count, result, task_output)

        if result["passed"]:
            return task_output, tool_cache_update

        # get new output from Task agent with correction feedback
        task_output, tool_cache_update = run_task(task, gene_symbol=gene, tool_results=tool_result, feedback=result["feedback"])

        # update best complete output after each retry
        if task_output.get("status") == "complete" and task_output.get("applies") is not None:
            last_complete_output = task_output

        retry_count += 1

    # check the final retry output before giving up
    result = check_reasoning(task_output, guideline_entry)
    _log_attempt("judge", criterion, variant, retry_count, result, task_output)
    if result["passed"]:
        return task_output, tool_cache_update

    # update last_complete_output one final time
    if task_output.get("status") == "complete" and task_output.get("applies") is not None:
        last_complete_output = task_output

    # return last complete output rather than nulling everything —
    # a flagged-but-complete result is better than applies=None causing LP→VUS
    if last_complete_output is not None:
        print(f"JUDGE AGENT: Retry limit hit for {criterion} — returning last complete output "
              f"(applies={last_complete_output.get('applies')}) with warning flag")
        last_complete_output["judge_warning"] = (
            f"Judge agent exceeded retry limit ({RETRY_LIMIT}); "
            f"output returned as-is with unresolved reasoning concerns"
        )
        return last_complete_output, tool_cache_update

    return {
        "criterion": task.get("criterion"),
        "evidence": None,
        "reasoning": None,
        "applies": None,
        "tool_used": None,
        "tool_input": None,
        "disease": task.get("disease"),
        "status": "error",
        "error": f"Judge agent exceeded retry limit ({RETRY_LIMIT}) without resolving reasoning error"
    }, tool_cache_update
