import requests
import json
from config import MODELS, OLLAMA_BASE_URL, RETRY_LIMIT
from agents.task_agent import run_task
from tools.utils import parse_json_response

OLLAMA_GENERATE_URL = f"{OLLAMA_BASE_URL}/api/generate"


def call_ollama(prompt: str) -> str:
    payload = {
        "model": MODELS["debug"],
        "prompt": prompt,
        "stream": False,
        "keep_alive": -1
    }
    response = requests.post(OLLAMA_GENERATE_URL, json=payload)
    response.raise_for_status()
    return response.json()["response"]


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
- evidence is null or missing
- tool call clearly failed (e.g. API error, variant not found)
- output fields are missing or malformed

Task output:
{json.dumps(task_output, indent=2)}

Respond ONLY with a JSON object in this exact format, no explanation:
{{
    "pass": <true | false>,
    "error_type": "technical",
    "feedback": "<if pass is false: specific instruction for the Task agent to fix the error. If pass is true: null>"
}}"""

    raw = call_ollama(prompt)

    clean = raw.strip()
    if clean.startswith("```"):
        clean = clean.split("```")[1]
        if clean.startswith("json"):
            clean = clean[4:]

    return parse_json_response(clean)


def run_debug(task: dict, retry_count: int = 0) -> dict:
    """
    Main entry point called by pipeline.py.
    Runs the Task agent, checks output, retries if technical error found.
    Returns the validated task output or a failure dict if retry limit hit.
    """
    # run the task agent fresh on first attempt
    task_output = run_task(task)

    while retry_count < RETRY_LIMIT:
        result = check_technical(task_output)

        if result["pass"]:
            # no technical errors, pass output forward to Judge agent
            return task_output

        # technical error found — retry Task agent with feedback
        print(f"DEBUG AGENT: Technical error detected (attempt {retry_count + 1}/{RETRY_LIMIT})")
        print(f"Feedback: {result['feedback']}")

        retry_count += 1
        task_output = run_task(task, feedback=result["feedback"])

    # retry limit hit
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
    }

# if __name__ == "__main__":

#     # -------------------------------------------------------------------------
#     # TEST 1: Clean task output — Debug agent should pass it through
#     # -------------------------------------------------------------------------
#     print("\n" + "="*60)
#     print("TEST 1: Clean output — expect pass=true")
#     print("="*60)

#     clean_task = {
#         "criterion": "PM2",
#         "variant": "NM_000020.3:c.557G>T",
#         "disease": "HHT"
#     }

#     result = run_debug(clean_task)
#     print(json.dumps(result, indent=2))

#     # -------------------------------------------------------------------------
#     # TEST 2: Nonexistent variant — tool should fail, Debug agent should retry
#     # -------------------------------------------------------------------------
#     print("\n" + "="*60)
#     print("TEST 2: Nonexistent variant — expect retry loop")
#     print("="*60)

#     bad_variant_task = {
#         "criterion": "PM2",
#         "variant": "NM_000000.0:c.9999Z>Q",
#         "disease": "HHT"
#     }

#     result = run_debug(bad_variant_task)
#     print(json.dumps(result, indent=2))

#     # -------------------------------------------------------------------------
#     # TEST 3: Injected error output — simulate Task agent returning status=error
#     # -------------------------------------------------------------------------
#     print("\n" + "="*60)
#     print("TEST 3: Injected error output — expect pass=false and feedback")
#     print("="*60)

#     from agents.debug_agent import check_technical

#     injected_error_output = {
#         "criterion": "PM2",
#         "evidence": None,
#         "reasoning": None,
#         "applies": None,
#         "tool_used": "gnomad",
#         "tool_input": "12-51914005-G-T",
#         "disease": "HHT",
#         "status": "error",
#         "error": "Variant not found"
#     }

#     result = check_technical(injected_error_output)
#     print(json.dumps(result, indent=2))

#     # -------------------------------------------------------------------------
#     # TEST 4: Injected clean output — simulate Task agent returning complete
#     # -------------------------------------------------------------------------
#     print("\n" + "="*60)
#     print("TEST 4: Injected clean output — expect pass=true")
#     print("="*60)

#     injected_clean_output = {
#         "criterion": "PM2",
#         "evidence": "Exome AC: 1, AN: 1461514, AF: 6.842e-07",
#         "reasoning": "AF is extremely low, supports PM2",
#         "applies": True,
#         "tool_used": "gnomad",
#         "tool_input": "12-51914005-G-T",
#         "disease": "HHT",
#         "status": "complete"
#     }

#     result = check_technical(injected_clean_output)
#     print(json.dumps(result, indent=2))