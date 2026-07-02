from agents.task_agent import run_task


if __name__ == "__main__":
    task = {
        "criterion": "PM2_SUPPORTING",
        "variant": "NM_000020.3:c.557G>T",
        "disease": "HHT",
        "tool": "gnomad",
        "instructions": (
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
        ),
        "hht_modification": "Supporting strength only; threshold: <6 total alleles in gnomAD OR <0.00004 in any subpopulation",
        "strength_override": "supporting",
    }
    result = run_task(
        task=task,
        tool_results=None,
        gene_symbol=None
    )

    print(result)