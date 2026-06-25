import json
from config import MODELS
import requests
from typing import Optional
from .llm import invoke_llm

# OLLAMA_GENERATE_URL = f"{OLLAMA_BASE_URL}/api/generate"

REQUIRED_FIELDS = [
    "criterion",
    "evidence",
    "reasoning",
    "applies",
    "tool_used",
    "tool_input",
    "disease",
    "status"
]

# def call_ollama(prompt: str) -> str:
#     payload = {
#         "model": MODELS["check"],
#         "prompt": prompt,
#         "stream": False,
#         "keep_alive": -1
#     }
#     response = requests.post(OLLAMA_GENERATE_URL, json=payload)
#     response.raise_for_status()
#     return response.json()["response"]



def call_judge_agent(prompt: str) -> str:
    response = invoke_llm(
        model=MODELS["check"]["model"],
        provider=MODELS["check"]["provider"],
        human_messsage=prompt,
    )
    return response


# def call_judge_agent(prompt: str, system_prompt: Optional[str] = None) -> str:
#     return invoke_llm("judge_agent", prompt)

def fix_formatting(task_output: dict) -> dict:
    """
    Fixes formatting errors in the task output deterministically where possible.
    Falls back to LLM only for fields that require rewriting.
    Returns the corrected output and a list of fixes applied.
    """
    output = task_output.copy()
    fixes = []

    # Fix 1: coerce applies to boolean
    applies = output.get("applies")
    if isinstance(applies, str):
        output["applies"] = applies.strip().lower() == "true"
        fixes.append(f"Coerced applies from string '{applies}' to boolean")

    # Fix 2: ensure status is "complete" or "error" — not None or missing
    if output.get("status") not in ("complete", "error"):
        output["status"] = "complete"
        fixes.append(f"Set status to 'complete' — was '{task_output.get('status')}'")

    # Fix 3: fill missing required fields with None
    for field in REQUIRED_FIELDS:
        if field not in output:
            output[field] = None
            fixes.append(f"Added missing field '{field}' as None")

    # Fix 4: remove unexpected error field on complete output
    if output.get("status") == "complete" and "error" in output:
        del output["error"]
        fixes.append("Removed error field from complete output")

    # Fix 5: if evidence or reasoning is empty string, set to None
    for field in ("evidence", "reasoning"):
        if output.get(field) == "":
            output[field] = None
            fixes.append(f"Set empty string '{field}' to None")

    return output, fixes


def check_format(task_output: dict) -> dict:
    """
    Checks task output for formatting errors.
    Returns a pass/fail dict with list of issues found.
    """
    issues = []

    # check all required fields present
    for field in REQUIRED_FIELDS:
        if field not in task_output:
            issues.append(f"Missing required field: '{field}'")

    # check applies is boolean
    applies = task_output.get("applies")
    if applies is not None and not isinstance(applies, bool):
        issues.append(f"Field 'applies' must be boolean, got {type(applies).__name__}: '{applies}'")

    # check status value
    status = task_output.get("status")
    if status not in ("complete", "error"):
        issues.append(f"Field 'status' must be 'complete' or 'error', got: '{status}'")

    # check evidence and reasoning are not empty strings
    for field in ("evidence", "reasoning"):
        if task_output.get(field) == "":
            issues.append(f"Field '{field}' is empty string — should be None or a value")

    # check error field only present when status is error
    if status == "complete" and "error" in task_output:
        issues.append("Field 'error' should not be present when status is 'complete'")

    return {
        "pass": len(issues) == 0,
        "issues": issues
    }


def run_check(task_output: dict) -> dict:
    """
    Main entry point called by pipeline.py.
    Checks formatting, fixes errors in place, returns corrected output.
    """
    result = check_format(task_output)

    if result["pass"]:
        print("CHECK AGENT: Output passed formatting check")
        return task_output

    print(f"CHECK AGENT: {len(result['issues'])} formatting issue(s) found:")
    for issue in result["issues"]:
        print(f"  - {issue}")

    corrected, fixes = fix_formatting(task_output)

    print(f"CHECK AGENT: Applied {len(fixes)} fix(es):")
    for fix in fixes:
        print(f"  - {fix}")

    # verify fixes resolved all issues
    recheck = check_format(corrected)
    if not recheck["pass"]:
        print("CHECK AGENT: Warning — some issues could not be fixed automatically:")
        for issue in recheck["issues"]:
            print(f"  - {issue}")

    return corrected


if __name__ == "__main__":

    # -------------------------------------------------------------------------
    # TEST 1: Clean output — should pass with no fixes
    # -------------------------------------------------------------------------
    print("\n" + "="*60)
    print("TEST 1: Clean output — expect pass, no fixes")
    print("="*60)

    clean_output = {
        "criterion": "PM2",
        "evidence": "Exome AC: 1, AN: 1461514, AF: 6.842e-07",
        "reasoning": "AF is extremely low (<0.001), supports PM2",
        "applies": True,
        "tool_used": "gnomad",
        "tool_input": "12-51914005-G-T",
        "disease": "HHT",
        "status": "complete"
    }

    result = run_check(clean_output)
    print(json.dumps(result, indent=2))

    # -------------------------------------------------------------------------
    # TEST 2: applies is string — should be coerced to boolean
    # -------------------------------------------------------------------------
    print("\n" + "="*60)
    print("TEST 2: applies as string — expect fix applied")
    print("="*60)

    string_applies_output = {
        "criterion": "PM2",
        "evidence": "Exome AC: 1, AN: 1461514, AF: 6.842e-07",
        "reasoning": "AF is extremely low (<0.001), supports PM2",
        "applies": "true",
        "tool_used": "gnomad",
        "tool_input": "12-51914005-G-T",
        "disease": "HHT",
        "status": "complete"
    }

    result = run_check(string_applies_output)
    print(json.dumps(result, indent=2))

    # -------------------------------------------------------------------------
    # TEST 3: Missing fields — should be added as None
    # -------------------------------------------------------------------------
    print("\n" + "="*60)
    print("TEST 3: Missing fields — expect fields added as None")
    print("="*60)

    missing_fields_output = {
        "criterion": "PM2",
        "evidence": "Exome AC: 1, AN: 1461514, AF: 6.842e-07",
        "applies": True,
        "status": "complete"
    }

    result = run_check(missing_fields_output)
    print(json.dumps(result, indent=2))

    # -------------------------------------------------------------------------
    # TEST 4: Empty string fields — should be set to None
    # -------------------------------------------------------------------------
    print("\n" + "="*60)
    print("TEST 4: Empty string fields — expect None")
    print("="*60)

    empty_fields_output = {
        "criterion": "PM2",
        "evidence": "",
        "reasoning": "",
        "applies": True,
        "tool_used": "gnomad",
        "tool_input": "12-51914005-G-T",
        "disease": "HHT",
        "status": "complete"
    }

    result = run_check(empty_fields_output)
    print(json.dumps(result, indent=2))

    # -------------------------------------------------------------------------
    # TEST 5: Error field present on complete output — should be removed
    # -------------------------------------------------------------------------
    print("\n" + "="*60)
    print("TEST 5: Spurious error field — expect removal")
    print("="*60)

    spurious_error_output = {
        "criterion": "PM2",
        "evidence": "Exome AC: 1, AN: 1461514, AF: 6.842e-07",
        "reasoning": "AF is extremely low (<0.001), supports PM2",
        "applies": True,
        "tool_used": "gnomad",
        "tool_input": "12-51914005-G-T",
        "disease": "HHT",
        "status": "complete",
        "error": ""
    }

    result = run_check(spurious_error_output)
    print(json.dumps(result, indent=2))