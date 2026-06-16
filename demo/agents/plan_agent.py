import requests
import json
from config import MODELS, OLLAMA_BASE_URL
from data.planrag import query
from tools.utils import extract_json_from_response

OLLAMA_GENERATE_URL = f"{OLLAMA_BASE_URL}/api/generate"


def call_ollama(prompt: str) -> str:
    payload = {
        "model": MODELS["plan"],
        "prompt": prompt,
        "stream": False,
        "keep_alive": -1
    }
    response = requests.post(OLLAMA_GENERATE_URL, json=payload)
    response.raise_for_status()
    return response.json()["response"]


def build_task_list(variant: str, disease: str, criteria: list[str]) -> list[dict]:
    """
    For each criterion, retrieves the PlanRAG entry and asks the LLM
    to confirm and structure the task.
    Returns a list of task dicts ready for the Task agent.
    """
    tasks = []

    for criterion in criteria:
        rag_entry = query(criterion)

        if rag_entry is None:
            print(f"PLAN AGENT: No PlanRAG entry found for {criterion}, skipping")
            continue

        prompt = f"""You are a variant classification assistant.

You are planning a classification task for the following variant and disease:
Variant: {variant}
Disease: {disease}
Criterion: {criterion}

Here are the instructions for evaluating this criterion:
{json.dumps(rag_entry, indent=2)}

Based on these instructions, produce a single task dict for this criterion.

Respond ONLY with a JSON object in this exact format, no explanation:
{{
    "criterion": "{criterion}",
    "variant": "{variant}",
    "disease": "{disease}",
    "tool": "{rag_entry['tool']}",
    "instructions": "<one sentence summarizing what the Task agent should do>"
}}"""

        raw = call_ollama(prompt)
        text = extract_json_from_response(raw)

        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        text = text.strip()

        start = text.find("{")
        end = text.rfind("}") + 1
        if start == -1 or end == 0:
            print(f"PLAN AGENT: Could not parse task for {criterion}, skipping")
            continue

        task = json.loads(text[start:end])
        tasks.append(task)

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


# if __name__ == "__main__":
#     tasks = run_plan(
#         variant="NM_000020.3:c.557G>T",
#         disease="HHT",
#         criteria=["PM2"]
#     )
#     print(json.dumps(tasks, indent=2))