import requests
import json
from config import MODELS, OLLAMA_BASE_URL, RETRY_LIMIT
from agents.task_agent import run_task
from tools.utils import parse_json_response
from data.planrag import query

OLLAMA_GENERATE_URL = f"{OLLAMA_BASE_URL}/api/generate"


def call_ollama(prompt: str) -> str:
    payload = {
        "model": MODELS["judge"],
        "prompt": prompt,
        "stream": False,
        "keep_alive": -1
    }
    response = requests.post(OLLAMA_GENERATE_URL, json=payload)
    response.raise_for_status()
    return response.json()["response"]


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
  (e.g. concluding PM2 applies when the allele frequency is above the threshold)
- The applies field contradicts the evidence and reasoning

Task output:
{json.dumps(task_output, indent=2)}

Respond ONLY with a JSON object in this exact format, no explanation:
{{
    "pass": <true | false>,
    "error_type": "reasoning",
    "feedback": "<if pass is false: specific instruction for the Task agent to fix the error. If pass is true: null>"
}}"""

    raw = call_ollama(prompt)

    return parse_json_response(raw)


def run_judge(task: dict, task_output: dict, retry_count: int = 0) -> dict:
    """
    Main entry point called by pipeline.py.
    Receives validated task output from Debug agent.
    Checks reasoning, retries Task agent only if reasoning error found.
    """
    criterion = task.get("criterion")
    rag_entry = query(criterion)

    if rag_entry is None:
        print(f"JUDGE AGENT: No PlanRAG entry found for {criterion}, proceeding without rules context")


    while retry_count < RETRY_LIMIT:
        result = check_reasoning(task_output, rag_entry)

        if result["pass"]:
            return task_output

        print(f"JUDGE AGENT: Reasoning error detected (attempt {retry_count + 1}/{RETRY_LIMIT})")
        print(f"Feedback: {result['feedback']}")

        retry_count += 1
        task_output = run_task(task, feedback=result["feedback"])

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
#         "criterion": "PM2",
#         "variant": "NM_000020.3:c.557G>T",
#         "disease": "HHT"
#     }

#     # -------------------------------------------------------------------------
#     # TEST 1: Clean output — Judge agent should pass it through without retrying
#     # -------------------------------------------------------------------------
#     print("\n" + "="*60)
#     print("TEST 1: Clean output — expect pass=true, no retry")
#     print("="*60)

#     clean_output = {
#         "criterion": "PM2",
#         "evidence": "Exome AC: 1, AN: 1461514, AF: 6.842e-07",
#         "reasoning": "AF is extremely low (<0.001), supports PM2",
#         "applies": True,
#         "tool_used": "gnomad",
#         "tool_input": "12-51914005-G-T",
#         "disease": "HHT",
#         "status": "complete"
#     }

#     result = run_judge(DEMO_TASK, clean_output)
#     print(json.dumps(result, indent=2))

#     # -------------------------------------------------------------------------
#     # TEST 2: Wrong tool used — ClinVar used for PM2 instead of gnomAD
#     # -------------------------------------------------------------------------
#     print("\n" + "="*60)
#     print("TEST 2: Wrong tool for criterion — expect reasoning error and retry")
#     print("="*60)

#     wrong_tool_output = {
#         "criterion": "PM2",
#         "evidence": "ClinVar shows 2 submissions: 1 VUS, 1 Likely Pathogenic",
#         "reasoning": "ClinVar submissions suggest the variant may be pathogenic, PM2 applies",
#         "applies": True,
#         "tool_used": "clinvar",
#         "tool_input": "NM_000020.3:c.557G>T",
#         "disease": "HHT",
#         "status": "complete"
#     }

#     result = run_judge(DEMO_TASK, wrong_tool_output)
#     print(json.dumps(result, indent=2))

#     # -------------------------------------------------------------------------
#     # TEST 3: Contradictory applies field — high AF but applies=true
#     # -------------------------------------------------------------------------
#     print("\n" + "="*60)
#     print("TEST 3: Contradictory applies field — expect reasoning error")
#     print("="*60)

#     contradictory_output = {
#         "criterion": "PM2",
#         "evidence": "Exome AC: 8500, AN: 1461514, AF: 0.0058",
#         "reasoning": "Variant is present in gnomAD with AF of 0.0058",
#         "applies": True,
#         "tool_used": "gnomad",
#         "tool_input": "12-51914005-G-T",
#         "disease": "HHT",
#         "status": "complete"
#     }

#     result = run_judge(DEMO_TASK, contradictory_output)
#     print(json.dumps(result, indent=2))

# # -------------------------------------------------------------------------
#     # TEST 4: check_reasoning in isolation — clean output
#     # -------------------------------------------------------------------------
#     print("\n" + "="*60)
#     print("TEST 4: check_reasoning in isolation — expect pass=true")
#     print("="*60)

#     rag_entry = query("PM2")
#     result = check_reasoning(clean_output, rag_entry)
#     print(json.dumps(result, indent=2))

#     # -------------------------------------------------------------------------
#     # TEST 5: check_reasoning in isolation — contradictory output
#     # -------------------------------------------------------------------------
#     print("\n" + "="*60)
#     print("TEST 5: check_reasoning in isolation — expect pass=false")
#     print("="*60)

#     result = check_reasoning(contradictory_output, rag_entry)
#     print(json.dumps(result, indent=2))