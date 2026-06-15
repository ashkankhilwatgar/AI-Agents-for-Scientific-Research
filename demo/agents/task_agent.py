import requests
import json
from config import MODELS, OLLAMA_BASE_URL
from tools.clinvar import search_clinvar
from tools.gnomad import query_gnomad
from tools.utils import hgvs_to_gnomad_format

OLLAMA_GENERATE_URL = f"{OLLAMA_BASE_URL}/api/generate"

TASK = {
    "criterion": "PM2",
    "variant": "NM_000020.3:c.557G>T",
    "disease": "HHT"
}

def call_ollama(prompt: str) -> str:
    payload = {
        "model": MODELS["task"],
        "prompt": prompt,
        "stream": False
    }
    response = requests.post(OLLAMA_GENERATE_URL, json=payload)
    response.raise_for_status()
    return response.json()["response"]


def select_tool(criterion: str, variant: str) -> dict:
    # only ask LLM to pick the tool, not the input
    prompt = f"""You are a variant classification assistant applying ACMG criteria.

Your task is to evaluate criterion {criterion} for variant {variant}.

You have access to the following tools:
- clinvar: searches ClinVar for existing variant classifications.
- gnomad: queries gnomAD for population allele frequency.

Respond ONLY with a JSON object in this exact format, no explanation:
{{
    "tool": "<clinvar | gnomad>",
    "reason": "<one sentence why this tool applies to {criterion}>"
}}"""

    raw = call_ollama(prompt)
    # ... parsing logic ...
    return json.loads(raw.strip())


def run_tool(tool_decision: dict, variant: str) -> dict:
    tool = tool_decision["tool"]
    # input is always the original variant — never trust the LLM for this
    input_value = variant

    print(f"DEBUG - tool: {tool}, input: {input_value}")

    if tool == "clinvar":
        return search_clinvar(input_value)
    elif tool == "gnomad":
        if input_value.startswith("NM_") or "c." in input_value or "p." in input_value:
            input_value = hgvs_to_gnomad_format(input_value)
            if isinstance(input_value, dict) and "error" in input_value:
                return input_value
        return query_gnomad(input_value)
    else:
        return {"error": f"Unknown tool: {tool}"}


def interpret_evidence(criterion: str, variant: str, disease: str, tool_used: str, evidence: dict) -> dict:
    """
    Step 3: Ask the LLM to interpret the tool output and map it to the ACMG criterion.
    Returns structured task output.
    """
    prompt = f"""You are a variant classification assistant applying ACMG criteria.

Variant: {variant}
Disease: {disease}
Criterion: {criterion}
Tool used: {tool_used}
Evidence retrieved:
{json.dumps(evidence, indent=2)}

Based on this evidence, determine whether criterion {criterion} applies.

Respond ONLY with a JSON object in this exact format, no explanation:
{{
    
    "criterion": "<ACMG criterion>",
    "evidence": "<concise summary of raw evidence>",
    "reasoning": "<how evidence maps to criterion>",
    "applies": "<true | false>",
    "tool_used": "<clinvar | gnomad | etc.>",
    "tool_input": "<exact input passed to the tool>",
    "disease": "<disease name>",
    "status": "<complete | error>",
    "error": "<error message if status is error, omit otherwise>"
    
}}"""

    raw = call_ollama(prompt)

    clean = raw.strip()
    if clean.startswith("```"):
        clean = clean.split("```")[1]
        if clean.startswith("json"):
            clean = clean[4:]


    output = json.loads(clean.strip())

    if isinstance(output.get("applies"), str):
        output["applies"] = output["applies"].strip().lower() == "true"

    return output

def run_task(task: dict, feedback: str = None, variant:str = "NM_000020.3:c.557G>T") -> dict:
    """
    Main entry point called by pipeline.py.
    If feedback is provided, it means this is a retry with a correction from Debug or Judge.
    """
    criterion = task["criterion"]
    variant = task["variant"]
    disease = task["disease"]

    # if this is a retry, let the LLM know what went wrong
    if feedback:
        prompt = f"""You are a variant classification assistant applying ACMG criteria.

Variant: {variant}
Disease: {disease}
Criterion: {criterion}

A previous attempt to evaluate this criterion failed with the following feedback:
{feedback}

Select the appropriate tool and input to retry this task.

You have access to the following tools:
- clinvar: searches ClinVar for existing variant classifications. Input: HGVS variant string.
- gnomad: queries gnomAD for population allele frequency. Input: gnomAD format (chrom-pos-ref-alt).

Respond ONLY with a JSON object in this exact format, no explanation:
{{
    "tool": "<clinvar | gnomad>",
    "input": "<exact input to pass to the tool>",
    "reason": "<one sentence why this tool applies to {criterion}>"
}}"""
        raw = call_ollama(prompt)
        clean = raw.strip()
        if clean.startswith("```"):
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]
        tool_decision = json.loads(clean.strip())
    else:
        tool_decision = select_tool(criterion, variant)

    # check tool selection itself didn't fail
    if "error" in tool_decision:
        return {
            "criterion": criterion,
            "evidence": None,
            "reasoning": None,
            "applies": None,
            "tool_used": None,
            "status": "error",
            "error": tool_decision["error"]
        }

    evidence = run_tool(tool_decision, task["variant"])

    if "error" in evidence:
        return {
            "criterion": criterion,
            "evidence": None,
            "reasoning": None,
            "applies": None,
            "tool_used": tool_decision["tool"],
            "status": "error",
            "error": evidence["error"]
        }

    return interpret_evidence(criterion, variant, disease, tool_decision["tool"], evidence)


# if __name__ == "__main__":
#     result = run_task(TASK)
#     print(json.dumps(result, indent=2))