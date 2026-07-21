import requests
import json
from data.planrag import query
from typing import Optional, TypeAlias
from config import MODELS
from data.planrag import get_gene_from_transcript
from collections import defaultdict
Tasks: TypeAlias = dict[str, list[dict[str, str]]]


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

    Returns a dict of task lists grouped by execution phase (phase1-phase4).
    """
    tasks = []

    # Detect gene from transcript so gene-specific planrag branches are used
    gene = None
    if variant.startswith("NM_") and ":" in variant:
        gene = get_gene_from_transcript(variant.split(":")[0])
        
    if gene:
        print(f"PLAN AGENT: Detected gene {gene} from transcript")
    
    if gene is None and gene_symbol:
        gene = gene_symbol
        print(f"PLAN AGENT: Gene {gene} resolved from VEP (transcript not mapped in GENE_DB)")  


    for criterion in criteria:
        rag_entry = query(criterion, gene=gene, disease=disease)

        if rag_entry is None:
            print(f"PLAN AGENT: No PlanRAG entry found for {criterion}, skipping")
            continue

        if rag_entry.get("excluded"):
            print(f"PLAN AGENT: {criterion} is excluded — {rag_entry.get('reason')}, skipping")
            continue

        if rag_entry.get("deferred"):
            print(f"PLAN AGENT: {criterion} is deferred (not automatable), skipping")
            continue

        task = {
            "criterion": criterion,
            "variant": variant,
            "disease": disease,
            "tool": rag_entry["tool"],
            "instructions": rag_entry["instructions"],
        }

        tasks.append(task)
        print(f"PLAN AGENT: Task created for {criterion}")

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
    Returns a dict of task lists (each a dict with "criterion", "variant",
    "disease", "tool", and "instructions") grouped by execution phase, for
    the Task agent to execute.
    """
    print(f"PLAN AGENT: Building task list for {variant} / {disease}")
    tasks = build_task_list(variant, disease, criteria, gene_symbol)
    print(f"PLAN AGENT: {len(tasks)} task(s) generated")
    return tasks
