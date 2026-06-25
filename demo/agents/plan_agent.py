import requests
import json
# from config import MODELS, OLLAMA_BASE_URL
from data.planrag import query
from tools.utils import parse_json_response
from .llm import invoke_llm
from typing import Optional

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


def call_plan_agent(prompt: str, system_prompt: Optional[str] = None) -> str:
    return invoke_llm("plan_agent", prompt)
    


def build_task_list(variant: str, disease: str, criteria: list[str]) -> list[dict]:
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
        print(f"PLAN AGENT: Detected gene {gene} from transcript")

    for criterion in criteria:
        rag_entry = query(criterion, gene=gene)

        if rag_entry is None:
            print(f"PLAN AGENT: No PlanRAG entry found for {criterion}, skipping")
            continue

        if rag_entry.get("excluded"):
            print(f"PLAN AGENT: {criterion} is excluded — {rag_entry.get('reason')}, skipping")
            continue

        if rag_entry.get("deferred"):
            print(f"PLAN AGENT: {criterion} is deferred (not automatable), skipping")
            continue

        prompt = f"""You are a variant classification assistant.

Variant: {variant}
Disease: {disease}
Criterion: {criterion}
Tool: {rag_entry['tool']}
Threshold: {rag_entry['threshold']}

Write one sentence describing what the Task agent should do to evaluate this criterion.

Respond ONLY with a JSON object in this exact format, no explanation:
{{
    "instructions": "<one sentence>"
}}"""
        raw = call_plan_agent(prompt)

        # raw = call_ollama(prompt)
        result = parse_json_response(raw)

        instructions = result.get("instructions", rag_entry["instructions"])

        task = {
            "criterion": criterion,
            "variant": variant,
            "disease": disease,
            "tool": rag_entry["tool"],
            "instructions": rag_entry["instructions"],
        }

        tasks.append(task)
        print(f"PLAN AGENT: Task created for {criterion}")

    # Sort by phase so dependencies are always evaluated before dependents
    tasks.sort(key=lambda t: (query(t["criterion"], gene=gene) or {}).get("phase", 99))

    return tasks


def run_plan(variant: str, disease: str, criteria: list[str]) -> list[dict]:
    """
    Main entry point called by pipeline.py.
    Returns a list of task dicts for the Task agent to execute.
    """
    print(f"PLAN AGENT: Building task list for {variant} / {disease}")
    tasks = build_task_list(variant, disease, criteria)
    print(f"PLAN AGENT: {len(tasks)} task(s) generated")
    return tasks
