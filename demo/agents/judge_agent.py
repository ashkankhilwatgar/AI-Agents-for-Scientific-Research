import requests
import json
# from config import MODELS, OLLAMA_BASE_URL, RETRY_LIMIT
from config import RETRY_LIMIT
from agents.task_agent import run_task
from tools.utils import parse_json_response
from data.planrag import query, get_gene_from_transcript
from .llm import invoke_llm
from typing import Optional
from config import MODELS

# OLLAMA_GENERATE_URL = f"{OLLAMA_BASE_URL}/api/generate"


# def call_ollama(prompt: str) -> str:
#     payload = {
#         "model": MODELS["judge"],
#         "prompt": prompt,
#         "stream": False,
#         "keep_alive": -1,
#         "options": {
#             "temperature": 0,
#             "num_predict": 2048
#         }
#     }
#     response = requests.post(OLLAMA_GENERATE_URL, json=payload)
#     response.raise_for_status()
#     return response.json()["response"]

# def call_judge_agent(prompt: str, system_prompt: Optional[str] = None) -> str:
#     return invoke_llm("judge_agent", prompt)

def call_judge_agent(prompt: str) -> str:
    response = invoke_llm(
        model=MODELS["judge"]["model"],
        provider=MODELS["judge"]["provider"],
        human_messsage=prompt
    )
    return response

def check_reasoning(task_output: dict, rag_entry: dict = None) -> dict:
    """
    Evaluates Task agent output for reasoning errors.
    Returns a pass/fail dict with feedback if failed.
    """
    rag_context = ""
    if rag_entry:
        rag_context = f"""
The following classification rules apply to this criterion:
{json.dumps(rag_entry, indent=2)}
Use these rules as the ground truth when evaluating whether the applies field is correct.
"""

    prompt = f"""You are a reasoning validator for a variant classification pipeline.
You are an expert bioinformatician with deep knowledge of ACMG variant classification criteria.

You will be given the output of a variant classification task. Your job is to check
for reasoning errors only — not technical issues.
{rag_context}
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
  provided the proband count. Do NOT ask the task agent to change tool_used to "lovd" or "erepo".
- A criterion applying at a lower strength than the maximum possible (e.g. PS4_Supporting instead of PS4_Strong)
  is valid if the proband count supports it.
- Evidence showing a variant is absent from a database — absence is valid evidence.

Task output:
{json.dumps(task_output, indent=2)}

Respond ONLY with a JSON object in this exact format, no explanation:
{{
    "pass": <true | false>,
    "error_type": "reasoning",
    "feedback": "<if pass is false: specific instruction for the Task agent to fix the error. If pass is true: null>"
}}"""
    raw = call_judge_agent(prompt)

    # raw = call_ollama(prompt)
    return parse_json_response(raw)


def run_judge(task: dict, task_output: dict, retry_count: int = 0) -> dict:
    """
    Main entry point called by pipeline.py.
    Receives validated task output from Debug agent.
    Checks reasoning, retries Task agent only if reasoning error found.
    """
    criterion = task.get("criterion")
    variant = task.get("variant", "")

    # Detect gene so gene-specific planrag rules (PVS1, PM1 boundaries) are
    # used as ground truth when the judge evaluates the task agent's reasoning.
    gene = None
    if variant.startswith("NM_") and ":" in variant:
        gene = get_gene_from_transcript(variant.split(":")[0])

    disease = task.get("disease")
    rag_entry = query(criterion, gene=gene, disease=disease)

    if rag_entry is None:
        print(f"JUDGE AGENT: No PlanRAG entry found for {criterion}, proceeding without rules context")

    while retry_count < RETRY_LIMIT:
        result = check_reasoning(task_output, rag_entry)

        if result["pass"]:
            return task_output

        print(f"JUDGE AGENT: Reasoning error detected (attempt {retry_count + 1}/{RETRY_LIMIT})")
        print(f"Feedback: {result['feedback']}")

        # get new output from Task agent with correction feedback
        task_output = run_task(task, feedback=result["feedback"])
        retry_count += 1

    # check the final retry output before giving up
    result = check_reasoning(task_output, rag_entry)
    if result["pass"]:
        return task_output

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
    }


# if __name__ == "__main__":

#     DEMO_TASK = {
#         "criterion": "PM2_SUPPORTING",
#         "variant": "NM_000020.3:c.557G>T",
#         "disease": "HHT",
#         "tool": "gnomad"
#     }

#     # -------------------------------------------------------------------------
#     # TEST 1: Clean output — Judge agent should pass it through without retrying
#     # -------------------------------------------------------------------------
#     print("\n" + "="*60)
#     print("TEST 1: Clean output — expect pass=true, no retry")
#     print("="*60)

#     clean_output = {
#         "criterion": "PM2_SUPPORTING",
#         "evidence": "Exome AC: 1, AN: 1461514, AF: 6.842e-07",
#         "reasoning": "Total allele count is 1 which is less than 6, PM2_Supporting applies",
#         "applies": True,
#         "tool_used": "gnomad",
#         "tool_input": "12-51914005-G-T",
#         "disease": "HHT",
#         "status": "complete"
#     }

#     result = run_judge(DEMO_TASK, clean_output)
#     print(json.dumps(result, indent=2))