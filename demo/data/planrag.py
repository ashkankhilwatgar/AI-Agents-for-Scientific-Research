# PlanRAG database
# Each entry contains the instructions the Plan agent uses to build a task.
# query() is the only interface plan_agent.py uses.
# When real RAG is added, replace the dict lookup in query() with vector search.
# The rest of the codebase does not need to change.

PLANRAG_DB = {
    "PM2": {
        "criterion": "PM2",
        "description": "Evaluate population allele frequency in gnomAD",
        "tool": "gnomad",
        "threshold": "AF < 0.001 in gnomAD exome and genome cohorts",
        "instructions": (
            "Query gnomAD for the allele frequency of the variant. "
            "PM2 applies if the variant is absent or extremely rare "
            "(AF < 0.001) in population databases. "
            "Use the gnomad tool with the variant in gnomAD format."
        )
    }
}


def query(criterion: str) -> dict | None:
    """
    Retrieves the PlanRAG entry for a given ACMG criterion.
    Returns None if no entry exists.
    When real RAG is implemented, replace the dict lookup below
    with a vector similarity search — this function signature stays the same.
    """
    return PLANRAG_DB.get(criterion.upper(), None)