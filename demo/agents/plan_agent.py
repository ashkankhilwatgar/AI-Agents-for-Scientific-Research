from data.planrag import query, get_gene_from_transcript


def build_task_list(variant: str, disease: str, criteria: list[str],gene_symbol = None) -> list[dict]:
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
    
    if gene is None and gene_symbol:              # ADD
        gene = gene_symbol
        print(f"PLAN AGENT: Gene {gene} resolved from VEP (not in GENE_DB)")  


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

    # Sort by phase so dependencies are always evaluated before dependents
    tasks.sort(key=lambda t: (query(t["criterion"], gene=gene, disease=disease) or {}).get("phase", 99))

    return tasks


def run_plan(variant: str, disease: str, criteria: list[str], gene_symbol = None) -> list[dict]:
    """
    Main entry point called by pipeline.py.
    Returns a list of task dicts for the Task agent to execute.
    """
    print(f"PLAN AGENT: Building task list for {variant} / {disease}")
    tasks = build_task_list(variant, disease, criteria, gene_symbol)
    print(f"PLAN AGENT: {len(tasks)} task(s) generated")
    return tasks
