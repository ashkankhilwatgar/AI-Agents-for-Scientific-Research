import requests
import json
# from config import MODELS, OLLAMA_BASE_URL
from data.planrag import query
# from tools.utils import parse_json_response
# from .llm.llm import invoke_llm
from typing import Optional, TypeAlias
from config import MODELS
from data.planrag import get_gene_from_transcript
from collections import defaultdict
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

Tasks: TypeAlias = dict[str, list[dict[str, str]]]
plan_console = Console()


def _plan_warning(message: str) -> None:
    """Render an actionable planning warning without verbose agent chatter."""
    warning = Text()
    warning.append("⚠ Plan agent: ", style="bold yellow")
    warning.append(message)
    plan_console.print(warning)


def _print_plan_summary(variant: str, disease: str, tasks: Tasks) -> None:
    """Render one compact summary after the complete task plan is built."""
    task_count = sum(len(phase_tasks) for phase_tasks in tasks.values())
    summary = Table.grid(padding=(0, 2))
    summary.add_column(style="bold cyan", no_wrap=True)
    summary.add_column()
    summary.add_row("Variant", Text(variant))
    summary.add_row("Disease", Text(disease))

    for phase_number in range(1, 5):
        phase_tasks = tasks.get(f"phase{phase_number}", [])
        criteria = ", ".join(task["criterion"] for task in phase_tasks)
        summary.add_row(f"Phase {phase_number}", Text(criteria or "—"))

    plan_console.print(Panel.fit(
        summary,
        title=Text("Plan Agent · Task Plan", style="bold cyan"),
        subtitle=Text(f"{task_count} task(s)", style="dim"),
        border_style="cyan" if task_count else "yellow",
        box=box.ROUNDED,
        padding=(1, 2),
    ))

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
        
    if gene is None and gene_symbol:              # ADD
        gene = gene_symbol


    for criterion in criteria:
        rag_entry = query(criterion, gene=gene, disease=disease)

        if rag_entry is None:
            _plan_warning(f"No PlanRAG entry for {criterion}; skipped.")
            continue

        if rag_entry.get("excluded"):
            _plan_warning(f"{criterion} excluded: {rag_entry.get('reason')}")
            continue

        if rag_entry.get("deferred"):
            _plan_warning(f"{criterion} is deferred and was not scheduled.")
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

    task = {
            "criterion": criterion,
            "variant": variant,
            "disease": disease,
            "tool": rag_entry["tool"],
            "instructions": rag_entry["instructions"],
        }
    """
    tasks = build_task_list(variant, disease, criteria, gene_symbol)
    _print_plan_summary(variant, disease, tasks)
    return tasks
