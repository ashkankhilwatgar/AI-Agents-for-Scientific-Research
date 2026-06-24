import requests
import json
from config import MODELS, OLLAMA_BASE_URL
from tools.clinvar import search_clinvar, search_clinvar_for_codon, search_clinvar_for_variant_ps4
from tools.gnomad import query_gnomad
from tools.utils import hgvs_to_gnomad_format, parse_json_response
from tools.computational import query_revel_spliceai, query_spliceai
from tools.vep import annotate_variant, _check_repeat_region, check_pm1_critical_region
from tools.pubmed import search_pubmed
from tools.erepo import search_erepo_by_position, search_erepo_for_variant
from tools.lovd import search_lovd_for_variant
from data.planrag import query, get_gene_from_transcript

OLLAMA_GENERATE_URL = f"{OLLAMA_BASE_URL}/api/generate"


def call_ollama(prompt: str) -> str:
    payload = {
        "model": MODELS["task"],
        "prompt": prompt,
        "stream": False,
        "keep_alive": -1,
        "options": {
            "temperature": 0,
            "num_predict": 1024
        }
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
- clinvar: searches ClinVar for variant classifications and proband counts. Use for PS4 (queries HHT VCEP submission for proband count, falls back to PubMed).
- gnomad: queries gnomAD for population allele frequency.
- revel_spliceai: fetches REVEL score and SpliceAI delta scores. Use for PP3 and BP4.
- spliceai: fetches SpliceAI delta scores only. Use for BP7 (synonymous/intronic variants).
- vep: annotates variant consequence, codon position, and NMD prediction. Use for PVS1, PM1, and PM4.
- pubmed: searches PubMed for case reports of the variant in HHT patients. Use for PS4.
- erepo: queries the ClinGen Evidence Repository for HHT VCEP-classified variants at the same protein position. Use for PS1 and PM5.
- lovd: queries the Leiden Open Variation Database for variant observations across labs. Use for PS4 when ClinVar and ERepo have no proband data.

Respond ONLY with a JSON object in this exact format, no explanation:
{{
    "tool": "<clinvar | gnomad | revel_spliceai | spliceai | vep | pubmed | erepo>",
    "reason": "<one sentence why this tool applies to {criterion}>"
}}"""

    raw = call_ollama(prompt)
    return parse_json_response(raw)


def run_tool(tool_decision: dict, variant: str, rag_entry: dict = None, gene: str = None) -> tuple[dict, str]:
    """
    Runs the selected tool and returns (result, actual_input_used).
    actual_input_used is the exact string passed to the API after any format conversion.
    """
    tool = tool_decision["tool"]
    input_value = variant

    print(f"DEBUG - tool: {tool}, input: {input_value}")

    if tool == "clinvar":
        criterion = (rag_entry or {}).get("criterion", "")
        if criterion == "PS4":
            # PS4: ClinVar VCEP SCV first (contains proband count), PubMed fallback
            cdna_change = input_value.split(":")[-1] if ":" in input_value else input_value
            print(f"DEBUG - PS4: querying ClinVar VCEP SCV for {input_value}")
            clinvar_ps4 = search_clinvar_for_variant_ps4(input_value)

            if "error" in clinvar_ps4:
                print(f"DEBUG - ClinVar PS4 lookup error: {clinvar_ps4['error']}, trying ERepo")
            elif clinvar_ps4.get("found") and clinvar_ps4.get("proband_count", 0) > 0:
                print(f"DEBUG - ClinVar PS4: {clinvar_ps4['proband_count']} proband(s) in HHT VCEP SCV")
                return clinvar_ps4, f"ClinVar VCEP SCV for {input_value}"
            else:
                print(f"DEBUG - ClinVar PS4: no proband count in SCV, trying ERepo")

            # ERepo fallback — VCEP curated evidence may contain proband count
            # even when the ClinVar SCV comment field is empty
            erepo_ps4 = search_erepo_for_variant(gene or "ACVRL1", cdna_change)
            if "error" not in erepo_ps4 and erepo_ps4.get("found"):
                proband_count = erepo_ps4.get("proband_count")
                classification = erepo_ps4.get("classification") or ""
                print(f"DEBUG - ERepo PS4: variant found | classification: {classification} | proband_count: {proband_count}")

                # If proband_count is not explicitly stated in the evidence notes,
                # infer it from the VCEP classification: P/LP requires patient-level evidence,
                # so treat it as ≥1 proband (PS4_Supporting threshold).
                if not proband_count:
                    if any(c in classification for c in ("Pathogenic", "Likely Pathogenic")):
                        proband_count = 1
                        print(f"DEBUG - ERepo PS4: proband_count inferred as 1 from VCEP {classification} classification")

                return {
                    "found": True,
                    "proband_count": proband_count,
                    "source": "ClinGen ERepo",
                    "classification": classification,
                    "evidence_notes": erepo_ps4.get("evidence_notes"),
                    "proband_count_note": (
                        "Proband count inferred from VCEP classification (≥1 required for P/LP); "
                        "not explicitly stated in evidence notes."
                        if proband_count == 1 and not erepo_ps4.get("proband_count")
                        else None
                    ),
                }, f"ERepo for {input_value}"
            else:
                print(f"DEBUG - ERepo PS4: variant not found, trying LOVD")

            # LOVD fallback — observation database across participating labs
            # Times_reported = number of independent lab submissions (proxy for probands)
            lovd_ps4 = search_lovd_for_variant(gene or "ACVRL1", cdna_change)
            if "error" not in lovd_ps4 and lovd_ps4.get("found"):
                times_reported = lovd_ps4.get("times_reported")
                print(f"DEBUG - LOVD PS4: variant found | times_reported: {times_reported}")
                if times_reported and times_reported > 0:
                    return {
                        "found": True,
                        "proband_count": times_reported,
                        "source": "LOVD",
                        "classification": None,
                        "evidence_notes": (
                            f"Variant observed {times_reported} time(s) in LOVD "
                            f"(Leiden Open Variation Database). LOVD is an observation "
                            f"database — Times_reported reflects independent lab submissions, "
                            f"not VCEP-curated pathogenicity."
                        ),
                    }, f"LOVD for {input_value}"
            else:
                print(f"DEBUG - LOVD PS4: variant not found, falling back to PubMed")

            # PubMed fallback with protein + nucleotide notation
            gene_label = gene or "ACVRL1"
            vep_result = annotate_variant(input_value)
            if "error" not in vep_result:
                protein_change   = vep_result.get("protein_change")
                protein_change_1 = vep_result.get("protein_change_1letter")
                if protein_change and protein_change_1:
                    pubmed_query = f"{gene_label} ({cdna_change} OR {protein_change} OR {protein_change_1}) HHT"
                elif protein_change:
                    pubmed_query = f"{gene_label} ({cdna_change} OR {protein_change}) HHT"
                else:
                    pubmed_query = f"{gene_label} {cdna_change} HHT"
            else:
                pubmed_query = f"{gene_label} {cdna_change} HHT"
            result = search_pubmed(pubmed_query)
            print(f"DEBUG - pubmed query: '{pubmed_query}' | total_found: {result.get('total_found', 'error')}")
            return result, pubmed_query
        else:
            return search_clinvar(input_value), input_value

    elif tool == "gnomad":
        if input_value.startswith("NM_") or "c." in input_value or "p." in input_value:
            converted = hgvs_to_gnomad_format(input_value)
            if isinstance(converted, dict) and "error" in converted:
                return converted, input_value
            input_value = converted
        return query_gnomad(input_value), input_value

    elif tool == "revel_spliceai":
        if input_value.startswith("NM_") or "c." in input_value or "p." in input_value:
            converted = hgvs_to_gnomad_format(input_value)
            if isinstance(converted, dict) and "error" in converted:
                return converted, input_value
            input_value = converted
        return query_revel_spliceai(input_value), input_value

    elif tool == "spliceai":
        return query_spliceai(input_value), input_value

    elif tool == "erepo":
        gene_label = gene or "ACVRL1"
        vep_result = annotate_variant(input_value)
        if "error" in vep_result:
            return vep_result, input_value
        codon_position = vep_result.get("codon_position")
        if codon_position is None:
            return {"error": "VEP did not return a protein position — cannot search ERepo"}, input_value
        result = search_erepo_by_position(gene_label, codon_position)
        # Remove the query variant itself from results — PS1/PM5 require other variants
        # at the same position. Match on the cdna change (e.g. "c.557G>T").
        query_cdna = input_value.split(":")[-1] if ":" in input_value else None
        if query_cdna and "classifications" in result:
            before = len(result["classifications"])
            result["classifications"] = [
                c for c in result["classifications"]
                if query_cdna not in c.get("hgvs", "")
            ]
            after = len(result["classifications"])
            print(f"DEBUG - erepo query: {gene_label} position {codon_position} | classifications found: {after} (filtered {before - after} self-match)")
        else:
            print(f"DEBUG - erepo query: {gene_label} position {codon_position} | classifications found: {len(result.get('classifications', []))}")

        # ClinVar fallback — if ERepo has no other variants at this codon,
        # search ClinVar for HHT VCEP-classified LP/P variants at the same position.
        if not result.get("classifications"):
            ref_aa = vep_result.get("amino_acid_ref")
            if ref_aa:
                print(f"DEBUG - erepo: 0 results, falling back to ClinVar for {ref_aa}{codon_position}")
                clinvar_result = search_clinvar_for_codon(
                    gene_label, codon_position, ref_aa, query_cdna
                )
                if "error" not in clinvar_result:
                    print(f"DEBUG - clinvar fallback: {len(clinvar_result.get('classifications', []))} LP/P variants found at codon {codon_position}")
                    result = clinvar_result
                else:
                    print(f"DEBUG - clinvar fallback error: {clinvar_result['error']}")

        return result, f"{gene_label} position {codon_position}"

    elif tool == "pubmed":
        # Generic PubMed search — PS4 now routes through the clinvar branch instead
        gene_label = gene or "ACVRL1"
        cdna_change = input_value.split(":")[-1] if ":" in input_value else input_value
        vep_result = annotate_variant(input_value)
        if "error" not in vep_result:
            protein_change   = vep_result.get("protein_change")
            protein_change_1 = vep_result.get("protein_change_1letter")
            if protein_change and protein_change_1:
                pubmed_query = f"{gene_label} ({cdna_change} OR {protein_change} OR {protein_change_1}) HHT"
            elif protein_change:
                pubmed_query = f"{gene_label} ({cdna_change} OR {protein_change}) HHT"
            else:
                pubmed_query = f"{gene_label} {cdna_change} HHT"
        else:
            pubmed_query = f"{gene_label} {cdna_change} HHT"
        result = search_pubmed(pubmed_query)
        print(f"DEBUG - pubmed query: '{pubmed_query}' | total_found: {result.get('total_found', 'error')}")
        return result, pubmed_query

    elif tool == "vep":
        vep_result = annotate_variant(input_value)
        if "error" in vep_result:
            return vep_result, input_value
        codon_position = vep_result.get("codon_position")
        critical_regions = (rag_entry or {}).get("critical_regions")
        if codon_position is not None and critical_regions is not None:
            pm1_check = check_pm1_critical_region(codon_position, critical_regions)
            vep_result["in_critical_region"] = pm1_check["in_critical_region"]
            vep_result["pm1_region_name"] = pm1_check["region_name"]
        return vep_result, input_value
    else:
        return {"error": f"Unknown tool: {tool}"}, input_value


def interpret_evidence(
    criterion: str,
    variant: str,
    disease: str,
    tool_used: str,
    tool_input: str,
    evidence: dict,
    rag_entry: dict = None,
    feedback: str = None
) -> dict:
    """
    Asks the LLM to interpret tool output and map it to the ACMG criterion.
    tool_input is the exact string passed to the API — set by code, not inferred by the LLM.
    rag_entry is injected as ground-truth rules so the LLM applies the correct thresholds.
    If feedback is provided (retry path), it is injected so the LLM knows
    exactly what it got wrong in the previous attempt.
    """
    rag_context = ""
    if rag_entry:
        rag_context = f"""
Classification rules for {criterion} (use these as ground truth):
- Threshold: {rag_entry.get('threshold', 'N/A')}
- Instructions: {rag_entry.get('instructions', 'N/A')}

Apply these rules exactly when setting the applies field.
"""

    feedback_block = ""
    if feedback:
        feedback_block = f"""
A previous interpretation of this evidence was rejected with the following feedback:
{feedback}

Correct this specific error in your response.
"""

    # applied_strength guidance — variable-strength criteria must set this explicitly.
    # Fixed-strength criteria are enforced in code below, so we tell the LLM to omit them.
    variable_strength_criteria = {"PVS1", "PS3", "PS4", "PM5", "PP1"}
    if criterion in variable_strength_criteria:
        strength_note = (
            '\n"applied_strength": "<very_strong | strong | moderate | supporting>  '
            '← set based on the strength level that applies per the instructions above",'
        )
    else:
        strength_note = '\n"applied_strength": null,  ← will be set automatically, leave null'

    prompt = f"""You are a variant classification assistant applying ACMG criteria.

Variant: {variant}
Disease: {disease}
Criterion: {criterion}
Tool used: {tool_used}
Evidence retrieved:
{json.dumps(evidence, indent=2)}
{rag_context}{feedback_block}
Based on this evidence, determine whether criterion {criterion} applies.

Respond ONLY with a JSON object in this exact format, no explanation:
IMPORTANT: "applies" must be an unquoted JSON boolean (true or false), not a string. Do not wrap it in quotes.
NOTE: Only include the "error" field if status is "error". Omit it entirely when status is "complete".
{{
    "criterion": "{criterion}",
    "evidence": "<concise summary of raw evidence>",
    "reasoning": "<how evidence maps to criterion>",
    "applies": <true | false>,{strength_note}
    "tool_used": "{tool_used}",
    "tool_input": "{tool_input}",
    "disease": "{disease}",
    "status": "<complete | error>"
}}"""

    raw = call_ollama(prompt)
    result = parse_json_response(raw)

    # enforce tool_used, tool_input, criterion, disease — never trust the LLM to set these correctly
    result["tool_used"] = tool_used
    result["tool_input"] = tool_input
    result["criterion"] = criterion
    result["disease"] = disease

    # enforce applied_strength for fixed-strength criteria
    # variable-strength criteria (PVS1, PS3, PS4, PM5, PP1) set their own applied_strength
    _FIXED_STRENGTH: dict[str, str] = {
        "PM2_SUPPORTING": "supporting",
        "PP3":            "supporting",
        "PP4_MODERATE":   "moderate",
        "PM1":            "moderate",
        "PM4":            "moderate",
        "PS1":            "strong",
        "PS2":            "strong",
        "BA1":            "benign_stand_alone",
        "BS1":            "benign_strong",
        "BS1_SUPPORTING": "benign_supporting",
        "BS3_SUPPORTING": "benign_supporting",
        "BS4":            "benign_strong",
        "BP2":            "benign_supporting",
        "BP4":            "benign_supporting",
        "BP5":            "benign_supporting",
        "BP7":            "benign_supporting",
    }
    if not result.get("applies"):
        # Criterion does not apply — applied_strength must be null.
        # Scoring only counts applied criteria, so this value is irrelevant,
        # but the judge agent flags non-null applied_strength on non-applied criteria.
        result["applied_strength"] = None
    else:
        fixed = _FIXED_STRENGTH.get(criterion)
        if fixed:
            result["applied_strength"] = fixed
        elif "applied_strength" not in result or result.get("applied_strength") is None:
            # variable-strength criterion but LLM didn't set it — default to criterion's base strength
            base = (rag_entry or {}).get("strength")
            result["applied_strength"] = base

    return result


def run_task(task: dict, feedback: str = None) -> dict:
    """
    Main entry point called by pipeline.py and by Debug/Judge agents on retry.

    First attempt: tool is taken directly from task["tool"] set by the Plan agent.
    No LLM call for tool selection — the plan already decided this.

    Retry (feedback is not None): LLM re-selects the tool using the feedback,
    and interpret_evidence() receives the feedback so it knows what to correct.

    rag_entry is queried once per task and passed into interpret_evidence() as
    ground-truth rules, so the LLM applies the correct thresholds on the first attempt.
    """
    criterion = task["criterion"]
    variant = task["variant"]
    disease = task["disease"]

    # Detect gene from transcript (NM_... prefix) so gene-specific planrag branches
    # and tool queries (erepo, PubMed) use the correct gene symbol.
    gene = None
    if variant.startswith("NM_") and ":" in variant:
        gene = get_gene_from_transcript(variant.split(":")[0])
    if gene:
        print(f"TASK AGENT: Detected gene {gene} from transcript")

    rag_entry = query(criterion, gene=gene)
    if rag_entry is None:
        print(f"TASK AGENT: No PlanRAG entry found for {criterion}, proceeding without rules context")

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

    evidence, actual_input = run_tool(tool_decision, variant, rag_entry=rag_entry, gene=gene)

    if "error" in evidence:
        return {
            "criterion": criterion,
            "evidence": None,
            "reasoning": None,
            "applies": None,
            "tool_used": tool_decision["tool"],
            "tool_input": actual_input,
            "disease": disease,
            "status": "error",
            "error": evidence["error"]
        }

    return interpret_evidence(
        criterion, variant, disease,
        tool_decision["tool"], actual_input, evidence,
        rag_entry=rag_entry,
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