import agents.task_agent as task_agent

PLANRAG_INSTRUCTIONS = (
            "Query gnomAD for the variant. Retrieve total allele count (AC) and per-subpopulation allele frequencies.\n"
            "Do NOT use Popmax FAF for this criterion — PM2 uses raw AC and subpopulation AF only.\n"
            "\n"
            "STEP 1: Is the variant absent from gnomAD entirely?\n"
            "  - YES → PM2_Supporting APPLIES. Set applies=true. Stop.\n"
            "  - NO  → continue to Step 2.\n"
            "\n"
            "STEP 2: Is total allele count (AC) across all gnomAD populations less than 6?\n"
            "  - AC < 6  → PM2_Supporting APPLIES. Set applies=true. Stop.\n"
            "  - AC >= 6 → continue to Step 3.\n"
            "\n"
            "STEP 3: Is allele frequency in ANY single gnomAD subpopulation less than 0.00004?\n"
            "  - ANY subpopulation AF < 0.00004 → PM2_Supporting APPLIES. Set applies=true. Stop.\n"
            "  - ALL subpopulation AFs >= 0.00004 → PM2_Supporting does NOT apply. Set applies=false.\n"
            "\n"
            "Record in evidence: which step triggered the decision and the exact values used."
        )

def test_run_task(monkeypatch):
    """
    Regression test: when tool_result returns an error, run_task should:

    1. Avoid sending failed evidence to interpret_evidence.
    2. Run the tool again
    """

    task = {
        "criterion": "PM2_SUPPORTING",
        "variant": "NM_000020.3:c.557G>T",
        "disease": "HHT",
        "tool": "gnomad",
        "instructions": PLANRAG_INSTRUCTIONS
    }

    tool_results = {"gnomad": {"evidence": {"error": f"ClinVar search failed after ..."}, "actual_input": "actual_input"}}

    def fake_select_tool(
            criterion, 
            variant, 
            disease = None, 
            feedback = None
    ):
        return {
            "tool": "gnomad",
            "description": "planrag specifies that we should use this tool"
        }
    
    monkeypatch.setattr(
        task_agent,
        "select_tool",
        fake_select_tool
    )

    run_tool_calls = []

    fake_actual_input = "NM_000020.3:c.557G>T"
    fake_evidence = "This is fake evidence"
    
    def fake_run_tool(
        tool_decision: dict, 
        variant: str, 
        rag_entry: dict | None = None, 
        gene: str | None = None, 
        disease: str | None = None
    ):
        run_tool_calls.append(
            {
                "tool_decision": "gnomad",
            }
        )
        return fake_evidence, fake_actual_input
    
    monkeypatch.setattr(
        task_agent,
        "run_tool",
        fake_run_tool
    )

    def fake_interpret_evidence(
        criterion: str,
        variant: str,
        disease: str,
        tool_used: str,
        tool_input: str,
        evidence: dict,
        rag_entry: dict | None = None,
        feedback: str | None = None,
        variant_type: str | None = None  
    ):
        return {
            "evidence": fake_evidence,
            "reasoning": "fake_reasoning",
            "applies": True,
            "applied_strength": "MODERATE",
            "status": "complete"
        }
    
    monkeypatch.setattr(
        task_agent,
        "interpret_evidence",
        fake_interpret_evidence
    )

    result, tool_cache_update = task_agent.run_task(
        task = task,
        tool_results=tool_results,
        gene_symbol=None
    )

    assert len(run_tool_calls) == 1
    assert tool_cache_update == {
        "gnomad": {
            "evidence": fake_evidence,
            "actual_input": fake_actual_input
        }
    }