import requests
import json
# from config import MODELS, OLLAMA_BASE_URL, RETRY_LIMIT
from config import RETRY_LIMIT
from agents.task_agent import run_task
# from tools.utils import parse_json_response
from .llm.llm import create_llm
from typing import Optional
from config import MODELS
from typing import Any, TypeAlias
from pydantic import BaseModel
from .llm.response_schema import CheckTechnicalResult

ToolResults: TypeAlias = dict[str, dict[str, Any]]

# OLLAMA_GENERATE_URL = f"{OLLAMA_BASE_URL}/api/generate"


# def call_ollama(prompt: str) -> str:
#     payload = {
#         "model": MODELS["debug"],
#         "prompt": prompt,
#         "stream": False,
#         "keep_alive": -1,
#         "options": {
#             "temperature": 0,
#             "num_predict": 512
#         }
#     }
#     response = requests.post(OLLAMA_GENERATE_URL, json=payload)
#     response.raise_for_status()
#     return response.json()["response"]

# def call_debug_agent(prompt: str, system_prompt: Optional[str] = None) -> str:
#     return invoke_llm("judge_agent", prompt)


def call_debug_agent(prompt: str, output_schema: type[BaseModel]) -> BaseModel:
    """
    Invoke the task LLM and return its response as a structured Pydantic object.

    The output_schema defines the expected response shape. Because
    with_structured_output() is used, the returned value is an instance of that
    schema, not a raw chat message and not response.content.
    """
    llm = create_llm(
        model=MODELS["debug"]["model"],
        provider=MODELS["debug"]["provider"],
        temperature=0
    )
    structured_llm = llm.with_structured_output(output_schema)
    response = structured_llm.invoke([{"role": "user", "content": prompt}])
    
    return response

    

def check_technical(task_output: dict) -> dict:
    """
    Evaluates Task agent output for technical errors.
    Technical errors are: tool call failures, missing data, API errors,
    malformed outputs, or status=error.
    Returns a pass/fail dict with feedback if failed.
    """
    prompt = f"""You are a technical validator for a bioinformatics pipeline.

You will be given the output of a variant classification task. Your job is to check
for technical errors only — not scientific reasoning.

Technical errors include:
- status is "error"
- evidence is null or missing entirely
- tool call clearly failed (e.g. API error message in evidence)
- required output fields (criterion, applies, reasoning, tool_used, tool_input, disease, status) are absent

The following are NOT technical errors — do not flag these:
- applied_strength being null when applies is false (null is correct here)
- revel_score being null for splice_region, splice_site, intronic, or synonymous variants (REVEL only scores missense variants)
- codon_position being null for intronic or splice_region variants (VEP does not return protein position for non-coding variants)
- A criterion not applying (applies: false) based on available evidence — this is a valid scientific conclusion, not a technical failure
- Evidence showing a variant is absent from a database — absence is valid evidence

You should follow the output schema

Some important rules: 
- The pass_ field is True when there are no technical errors, and False otherwise.
- The error_type field must explain why the pass_ field is True or False.
- If the output does not pass, the feedback field must contain guidance for the downstream task agent on how to fix the error.
"""
    result = call_debug_agent(prompt, CheckTechnicalResult).model_dump()

    # raw = call_ollama(prompt)
    return result


_REQUIRED_FIELDS = {"criterion", "applies", "reasoning", "evidence",
                    "tool_used", "tool_input", "disease", "status"}


def _deterministic_check(task_output: dict) -> bool:
    """
    Fast structural check that runs before the LLM.
    Returns True (pass) when the output is clearly valid:
      - status is "complete"
      - applies is a boolean
      - all required fields are present (values may be null — null is valid)
      - no top-level "error" key
    Returns False only when there is a genuine structural problem.
    The LLM check is only invoked when this returns False.
    """
    if task_output.get("status") == "error":
        return False
    if not isinstance(task_output.get("applies"), bool):
        return False
    if "error" in task_output:
        return False
    for field in _REQUIRED_FIELDS:
        if field not in task_output:
            return False
    return True


def run_debug(task: dict, gene_symbol: str | None, tool_results: ToolResults | None, retry_count: int = 0) -> tuple[dict, dict]:
    """
    Main entry point called by pipeline.py.
    Runs the Task agent, checks output, retries if technical error found.

    Order of checks:
      1. Deterministic structural check — fast, no LLM, no false positives.
         Passes immediately when output is well-formed (applies is bool,
         required fields present, status != error). Null field values are
         always valid — null REVEL for splice variants, null codon_position
         for intronic variants, null applied_strength when applies=False, etc.
      2. LLM check — only runs when the deterministic check finds a genuine
         structural problem (status=error, missing fields, non-boolean applies).

    Returns the validated task output or a failure dict if retry limit hit.
    """
    task_output, tool_cache_update = run_task(task, gene_symbol=gene_symbol, tool_results = tool_results)

    while retry_count < RETRY_LIMIT:
        # Fast path: structurally valid output skips LLM entirely
        if _deterministic_check(task_output):
            return task_output, tool_cache_update

        # Slow path: genuine structural problem — ask LLM for specific feedback
        result = check_technical(task_output)

        if result["past"]:
            return task_output, tool_cache_update


        task_output, tool_cache_update = run_task(
            task, 
            tool_results = tool_results, 
            gene_symbol=gene_symbol,
            feedback=result["feedback"]
        )
        retry_count += 1

    # check the final retry output before giving up
    if _deterministic_check(task_output):
        return task_output, tool_cache_update

    result = check_technical(task_output)
    if result["past"]:
        return task_output, tool_cache_update

    return {
        "criterion": task.get("criterion"),
        "evidence": None,
        "reasoning": None,
        "applies": None,
        "tool_used": None,
        "tool_input": None,
        "disease": task.get("disease"),
        "status": "error",
        "error": f"Debug agent exceeded retry limit ({RETRY_LIMIT}) without resolving technical error"
    }, tool_cache_update


# if __name__ == "__main__":

#     # -------------------------------------------------------------------------
#     # TEST 1: Clean task output — Debug agent should pass it through
#     # -------------------------------------------------------------------------
#     log("\n" + "="*60)
#     log("TEST 1: Clean output — expect pass=true")
#     log("="*60)

#     clean_task = {
#         "criterion": "PM2_SUPPORTING",
#         "variant": "NM_000020.3:c.557G>T",
#         "disease": "HHT",
#         "tool": "gnomad"
#     }

#     result = run_debug(clean_task)
#     log(json.dumps(result, indent=2))

#     # -------------------------------------------------------------------------
#     # TEST 2: Nonexistent variant — tool should fail, Debug agent should retry
#     # -------------------------------------------------------------------------
#     log("\n" + "="*60)
#     log("TEST 2: Nonexistent variant — expect retry loop")
#     log("="*60)

#     bad_variant_task = {
#         "criterion": "PM2_SUPPORTING",
#         "variant": "NM_000000.0:c.9999Z>Q",
#         "disease": "HHT",
#         "tool": "gnomad"
#     }

#     result = run_debug(bad_variant_task)
#     log(json.dumps(result, indent=2))