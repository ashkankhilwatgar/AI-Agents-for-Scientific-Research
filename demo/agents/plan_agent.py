import requests
import json
# from config import MODELS, OLLAMA_BASE_URL
from data.planrag import query
# from tools.utils import parse_json_response
from .llm.llm import invoke_llm
from typing import Optional, TypeAlias
from config import MODELS
from data.planrag import get_gene_from_transcript
from collections import defaultdict
Tasks: TypeAlias = dict[str, list[dict[str, str]]]

# OLLAMA_GENERATE_URL = f"{OLLAMA_BASE_URL}/api/generate"


# def call_ollama(prompt: str) -> str:
#     payload = {
#         "model": MODELS["plan"],
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


# def call_plan_agent(prompt: str, system_prompt: Optional[str] = None) -> str:
#     return invoke_llm("plan_agent", prompt)

def call_plan_agent(prompt: str) -> str:
    response = invoke_llm(
        model=MODELS["plan"]["model"],
        provider=MODELS["plan"]["provider"],
        human_messsage=prompt
    )
    return response
    


def build_task_list(variant: str, disease: str, criteria: list[str],gene_symbol = None) -> dict[str, list]:
    """
    For each criterion, retrieves the PlanRAG entry and builds a task dict
    for the Task agent. All fields are set deterministically from the RAG entry —
    no LLM call is made here. The Task agent has access to the full RAG entry
    (including detailed instructions) at evaluation time.

    Returns a list of task dicts sorted by execution phase.
    """
    tasks = []

    # Detect gene from transcript so gene-specific planrag branches are used
    gene = None
    if variant.startswith("NM_") and ":" in variant:
        gene = get_gene_from_transcript(variant.split(":")[0])
        
    if gene:
        pass

    if gene is None and gene_symbol:              # ADD
        gene = gene_symbol


    for criterion in criteria:
        rag_entry = query(criterion, gene=gene, disease=disease)

        if rag_entry is None:
            continue

        if rag_entry.get("excluded"):
            continue

        if rag_entry.get("deferred"):
            continue

#         prompt = f"""You are a variant classification assistant.

# Variant: {variant}
# Disease: {disease}
# Criterion: {criterion}
# Tool: {rag_entry['tool']}
# Threshold: {rag_entry['threshold']}

# Write one sentence describing what the Task agent should do to evaluate this criterion.

# Respond ONLY with a JSON object in this exact format, no explanation:
# {{
#     "instructions": "<one sentence>"
# }}"""
#         raw = call_plan_agent(prompt)

#         # raw = call_ollama(prompt)
#         result = parse_json_response(raw)

#         instructions = result.get("instructions", rag_entry["instructions"])

        task = {
            "criterion": criterion,
            "variant": variant,
            "disease": disease,
            "tool": rag_entry["tool"],
            "instructions": rag_entry["instructions"],
        }

        tasks.append(task)

    result = defaultdict(list)

    for task in tasks:
        rag_entry = query(task["criterion"], gene=gene, disease=disease) or {}

        phase = rag_entry.get("phase", 4)

        # Defensive normalization (in case phase is string or invalid)
        try:
            phase = int(phase)
        except (TypeError, ValueError):
            phase = 4

        phase_key = f"phase {phase}" 

        result[phase_key].append(task)

    return {
        "phase1": result.get("phase 1", []),
        "phase2": result.get("phase 2", []),
        "phase3": result.get("phase 3", []),
        "phase4": result.get("phase 4", []),
    }


def run_plan(variant: str, disease: str, criteria: list[str], gene_symbol = None) -> Tasks:
    """
    Main entry point called by pipeline.py.
    Returns a list of task dicts for the Task agent to execute.
    """
    tasks = build_task_list(variant, disease, criteria, gene_symbol)
    return tasks
