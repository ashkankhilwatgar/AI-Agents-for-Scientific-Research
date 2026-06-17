import requests
import json
from config import MODELS, OLLAMA_BASE_URL
from tools.clinvar import search_clinvar
from tools.gnomad import query_gnomad
from tools.utils import hgvs_to_gnomad_format, parse_json_response
from tools.computational import query_revel_spliceai, query_spliceai

OLLAMA_GENERATE_URL = f"{OLLAMA_BASE_URL}/api/generate"


def call_ollama(prompt: str) -> str:
    payload = {
        "model": MODELS["task"],
        "prompt": prompt,
        "stream": False,
        "keep_alive": -1
    }
    response = requests.post(OLLAMA_GENERATE_URL, json=payload)
    response.raise_for_status()
    return response.json()["response"]


def select_tool(criterion: str, variant: str, feedback: str = None) -> dict:
    """
    Called only on retry — first attempt always uses task["tool"] from the plan.
    feedback is the Judge agent's correction from the previous attempt.
    """
    feedback_block = ""
    if feedback:
        feedback_block = f"""
A previous attempt to evaluate this criterion failed with the following feedback:
{feedback}

Use this feedback to select the correct tool.
"""

    prompt = f"""You are a variant classification assistant applying ACMG criteria.

Your task is to evaluate criterion {criterion} for variant {variant}.
{feedback_block}
You have access to the following tools:
- clinvar: searches ClinVar for existing variant classifications.
- gnomad: queries gnomAD for population allele frequency.
- revel_spliceai: fetches REVEL score and SpliceAI delta scores. Use for PP3 and BP4.
- spliceai: fetches SpliceAI delta scores only. Use for BP7 (synonymous/intronic variants).

Respond ONLY with a JSON object in this exact format, no explanation:
{{
    "tool": "<clinvar | gnomad | revel_spliceai | spliceai>",
    "reason": "<one sentence why this tool applies to {criterion}>"
}}"""

    raw = call_ollama(prompt)
    return parse_json_response(raw)


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
    elif tool == "revel_spliceai":
        if input_value.startswith("NM_") or "c." in input_value or "p." in input_value:
            gnomad = hgvs_to_gnomad_format(input_value)
            if isinstance(gnomad, dict) and "error" in gnomad:
                return gnomad
            input_value = gnomad
        return query_revel_spliceai(input_value)
    elif tool == "spliceai":
        return query_spliceai(input_value)
    else:
        return {"error": f"Unknown tool: {tool}"}


def interpret_evidence(
    criterion: str,
    variant: str,
    disease: str,
    tool_used: str,
    evidence: dict,
    feedback: str = None
) -> dict:
    """
    Asks the LLM to interpret tool output and map it to the ACMG criterion.
    If feedback is provided (retry path), it is injected so the LLM knows
    exactly what it got wrong in the previous attempt.
    """
    feedback_block = ""
    if feedback:
        feedback_block = f"""
A previous interpretation of this evidence was rejected with the following feedback:
{feedback}

Correct this specific error in your response.
"""

    prompt = f"""You are a variant classification assistant applying ACMG criteria.

Variant: {variant}
Disease: {disease}
Criterion: {criterion}
Tool used: {tool_used}
Evidence retrieved:
{json.dumps(evidence, indent=2)}
{feedback_block}
Based on this evidence, determine whether criterion {criterion} applies.

Respond ONLY with a JSON object in this exact format, no explanation:
{{
    "criterion": "<ACMG criterion>",
    "evidence": "<concise summary of raw evidence>",
    "reasoning": "<how evidence maps to criterion>",
    "applies": "<true | false>",
    "tool_used": "<clinvar | gnomad | revel_spliceai | spliceai>",
    "tool_input": "<exact input passed to the tool>",
    "disease": "<disease name>",
    "status": "<complete | error>",
    "error": "<error message if status is error, omit otherwise>"
}}"""

    raw = call_ollama(prompt)
    return parse_json_response(raw)


def run_task(task: dict, feedback: str = None) -> dict:
    """
    Main entry point called by pipeline.py and by Debug/Judge agents on retry.

    First attempt: tool is taken directly from task["tool"] set by the Plan agent.
    No LLM call for tool selection — the plan already decided this.

    Retry (feedback is not None): LLM re-selects the tool using the feedback,
    and interpret_evidence() receives the feedback so it knows what to correct.
    """
    criterion = task["criterion"]
    variant = task["variant"]
    disease = task["disease"]

    if feedback:
        # retry path — LLM re-selects tool with correction context
        tool_decision = select_tool(criterion, variant, feedback=feedback)
    else:
        # first attempt — trust the plan, no LLM call
        tool_decision = {"tool": task["tool"], "reason": "specified by Plan agent"}

    # check tool selection itself didn't fail
    if "error" in tool_decision:
        return {
            "criterion": criterion,
            "evidence": None,
            "reasoning": None,
            "applies": None,
            "tool_used": None,
            "tool_input": None,
            "disease": disease,
            "status": "error",
            "error": tool_decision["error"]
        }

    evidence = run_tool(tool_decision, variant)

    if "error" in evidence:
        return {
            "criterion": criterion,
            "evidence": None,
            "reasoning": None,
            "applies": None,
            "tool_used": tool_decision["tool"],
            "tool_input": variant,
            "disease": disease,
            "status": "error",
            "error": evidence["error"]
        }

    return interpret_evidence(
        criterion, variant, disease,
        tool_decision["tool"], evidence,
        feedback=feedback
    )


# if __name__ == "__main__":
#     result = run_task({
#         "criterion": "PP3",
#         "variant": "NM_000020.3:c.557G>T",
#         "disease": "HHT",
#         "tool": "revel_spliceai"
#     })
#     print(json.dumps(result, indent=2))