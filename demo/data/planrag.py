# PlanRAG database — HHT VCEP criteria
#
# Covers all 22 active HHT VCEP criteria (28 total minus 6 excluded by VCEP).
# Excluded: PS2, PM6, PM3, BS2, BP2, BP5 — not in this file.
#
# Automation tiers:
#   "fully_automatable"   — pipeline evaluates end-to-end
#   "partially_automatable" — tool fetch is deterministic; LLM must judge quality
#   "not_automatable"     — flag and defer; no tool can provide the required data
#
# Strengths (ACMG/ClinGen):
#   "very_strong", "strong", "moderate", "supporting", "stand_alone"
#
# query() is the only interface used by plan_agent.py and judge_agent.py.
# When real vector RAG replaces this dict, only the internals of query() change.

PLANRAG_DB = {

    # ──────────────────────────────────────────────────────────────────────────
    # FULLY AUTOMATABLE — pipeline can evaluate end-to-end
    # ──────────────────────────────────────────────────────────────────────────

    "PVS1": {
        "criterion": "PVS1",
        "acmg_category": "Pathogenic",
        "strength": "very_strong",
        "automation": "fully_automatable",
        "tool": "vep",
        "description": (
            "Null variant in a gene where loss-of-function is a known disease mechanism. "
            "HHT VCEP applies gene-specific strength adjustments: "
            "ENG initiation codon variants → PVS1_Strong; "
            "ACVRL1 initiation codon variants → PVS1_Moderate. "
            "Use the AutoPVS1 decision tree for all other PVS1-eligible variant types."
        ),
        "threshold": None,
        "instructions": (
            "Use VEP to annotate the variant consequence. "
            "If the variant is a null type (nonsense, frameshift, splice-site ±1/2, initiation codon, "
            "single/multi-exon deletion), apply the PVS1 decision tree via AutoPVS1. "
            "For ENG initiation codon variants, cap strength at PVS1_Strong. "
            "For ACVRL1 initiation codon variants, cap strength at PVS1_Moderate. "
            "Record the final strength level in the output, not just true/false."
        ),
        "hht_modification": "ENG initiation codon → PVS1_Strong; ACVRL1 initiation codon → PVS1_Moderate",
        "strength_override": None,
    },

    "PM2_SUPPORTING": {
        "criterion": "PM2_Supporting",
        "acmg_category": "Pathogenic",
        "strength": "supporting",
        "automation": "fully_automatable",
        "tool": "gnomad",
        "description": (
            "Variant is absent or extremely rare in population databases. "
            "HHT VCEP downgraded this from PM2_Moderate to PM2_Supporting. "
            "Use Popmax/Grpmax Filtering Allele Frequency (FAF), not raw AF."
        ),
        "threshold": "Popmax FAF < 0.0001 (absent or extremely rare in gnomAD)",
        "instructions": (

            "Query gnomAD for the allele frequency of the variant. "
            "PM2 applies if the variant is absent or has allele frequency < 0.001"
            "(AF < 0.001) in population databases. "
            "Use the gnomad tool with the variant in gnomAD format."
        ),
        "hht_modification": "Downgraded from PM2_Moderate to PM2_Supporting; use Popmax/Grpmax FAF",
        "strength_override": "supporting",
    },

    "BA1": {
        "criterion": "BA1",
        "acmg_category": "Benign",
        "strength": "stand_alone",
        "automation": "fully_automatable",
        "tool": "gnomad",
        "description": (
            "Allele frequency is above the disease-specific threshold — variant is common enough "
            "to be stand-alone benign. HHT VCEP uses a gene-specific MAF threshold "
            "based on HHT prevalence. Use Popmax FAF."
        ),
        "threshold": "Popmax FAF ≥ 0.01 (HHT VCEP threshold)",
        "instructions": (
            "Query gnomAD for the Popmax Filtering Allele Frequency (FAF). "
            "BA1 applies if Popmax FAF ≥ 0.01. "
            "This is a stand-alone benign criterion — if it applies, "
            "the variant is classified Benign regardless of other evidence. "
            "Flag this to the Scoring agent immediately if BA1 applies."
        ),
        "hht_modification": "HHT-specific MAF threshold; Popmax FAF applicable",
        "strength_override": "stand_alone",
    },

    "BS1": {
        "criterion": "BS1",
        "acmg_category": "Benign",
        "strength": "strong",
        "automation": "fully_automatable",
        "tool": "gnomad",
        "description": (
            "Allele frequency is higher than expected for the disorder — strong benign evidence. "
            "HHT VCEP uses a conservative threshold below BA1. "
            "BS1_Supporting is also defined by HHT VCEP as an additional strength level."
        ),
        "threshold": "Popmax FAF ≥ 0.001 and < 0.01 → BS1; FAF ≥ 0.0001 and < 0.001 → BS1_Supporting",
        "instructions": (
            "Query gnomAD for the Popmax FAF. "
            "If Popmax FAF ≥ 0.001 and < 0.01: BS1 applies (Strong). "
            "If Popmax FAF ≥ 0.0001 and < 0.001: BS1_Supporting applies. "
            "Record the exact strength level — BS1 and BS1_Supporting are scored differently. "
            "If BA1 already applies, do not also apply BS1."
        ),
        "hht_modification": "HHT-specific threshold; BS1_Supporting also defined",
        "strength_override": None,
    },

    "PP2": {
        "criterion": "PP2",
        "acmg_category": "Pathogenic",
        "strength": "supporting",
        "automation": "fully_automatable",
        "tool": "gnomad",
        "description": (
            "Missense variant in a gene with a low rate of benign missense variation. "
            "ENG and ACVRL1 both meet this criterion based on gnomAD missense constraint "
            "(z-score). This is a gene-level metric, not a variant-level lookup."
        ),
        "threshold": "Missense z-score > 3.09 (gnomAD constraint metric indicating low benign missense tolerance)",
        "instructions": (
            "First check whether the variant is a missense variant (amino acid change, not synonymous). "
            "If not missense, PP2 does not apply — return applies=false immediately. "
            "If missense, fetch the gnomAD gene constraint metrics for the gene (ENG or ACVRL1). "
            "PP2 applies if the missense z-score exceeds 3.09 (gene is intolerant of benign missense). "
            "ENG and ACVRL1 both meet this threshold — you can apply PP2 directly for missense "
            "variants in these genes without fetching the metric each time."
        ),
        "hht_modification": None,
        "strength_override": None,
    },

    "PP3": {
        "criterion": "PP3",
        "acmg_category": "Pathogenic",
        "strength": "supporting",
        "automation": "fully_automatable",
        "tool": "revel_spliceai",
        "description": (
            "Multiple lines of computational evidence support a deleterious effect. "
            "HHT VCEP specifies exact score thresholds: REVEL ≥ 0.644 for missense; "
            "SpliceAI ≥ 0.2 for splice impact."
        ),
        "threshold": "REVEL ≥ 0.644 (missense) OR SpliceAI delta score ≥ 0.2 (splice)",
        "instructions": (
            "For missense variants: fetch REVEL score. PP3 applies if REVEL ≥ 0.644. "
            "For intronic or synonymous variants: fetch SpliceAI delta score. PP3 applies if any "
            "SpliceAI delta score (DS_AG, DS_AL, DS_DG, DS_DL) ≥ 0.2. "
            "Do not apply both REVEL and SpliceAI thresholds to the same variant — use the "
            "appropriate score for the variant type. "
            "Record the exact score retrieved and which threshold was applied."
        ),
        "hht_modification": "HHT VCEP defines specific thresholds: REVEL ≥ 0.644; SpliceAI ≥ 0.2",
        "strength_override": None,
    },

    "BP4": {
        "criterion": "BP4",
        "acmg_category": "Benign",
        "strength": "supporting",
        "automation": "fully_automatable",
        "tool": "spliceai",
        "description": (
            "Multiple lines of computational evidence suggest no impact on gene product. "
            "HHT VCEP uses SpliceAI ≤ 0.1 for synonymous and intronic variants. "
            "Can be combined with BP7."
        ),
        "threshold": "SpliceAI max delta score ≤ 0.1 for synonymous or intronic variants",
        "instructions": (
            "BP4 applies only to synonymous or deep intronic variants. "
            "Fetch SpliceAI scores for the variant. "
            "BP4 applies if all SpliceAI delta scores (DS_AG, DS_AL, DS_DG, DS_DL) ≤ 0.1. "
            "If any delta score > 0.1, BP4 does not apply. "
            "Note whether BP7 also applies — these two can be combined per HHT VCEP rules."
        ),
        "hht_modification": "SpliceAI ≤ 0.1 for synonymous/intronic; can combine with BP7",
        "strength_override": None,
    },

    "BP7": {
        "criterion": "BP7",
        "acmg_category": "Benign",
        "strength": "supporting",
        "automation": "fully_automatable",
        "tool": "spliceai",
        "description": (
            "Synonymous variant with no predicted splice impact. "
            "HHT VCEP requires SpliceAI ≤ 0.1 and confirms variant does not affect a conserved "
            "splice site. Can be combined with BP4."
        ),
        "threshold": "SpliceAI ≤ 0.1 AND variant is synonymous (no amino acid change)",
        "instructions": (
            "Check that the variant is synonymous (no amino acid change). "
            "If not synonymous, BP7 does not apply. "
            "If synonymous, fetch SpliceAI delta scores. "
            "BP7 applies if all SpliceAI delta scores ≤ 0.1. "
            "Note whether BP4 also applies — HHT VCEP allows combining BP4 + BP7."
        ),
        "hht_modification": "SpliceAI ≤ 0.1; combine with BP4 per HHT VCEP combining rules",
        "strength_override": None,
    },

    "PP5": {
        "criterion": "PP5",
        "acmg_category": "Pathogenic",
        "strength": "supporting",
        "automation": "fully_automatable",
        "tool": "clinvar",
        "description": (
            "Reputable source recently reports variant as pathogenic with supporting evidence. "
            "HHT VCEP uses ClinVar ≥ 2-star review status as the reputable source threshold."
        ),
        "threshold": "ClinVar classification = Pathogenic AND review status ≥ 2 stars (reviewed by expert panel or practice guideline)",
        "instructions": (
            "Search ClinVar for the variant. "
            "PP5 applies if ClinVar reports the variant as Pathogenic AND the review status "
            "is 2 or more stars (criteria provided by multiple submitters, expert panel, or practice guideline). "
            "1-star or 0-star ClinVar entries do not satisfy PP5. "
            "Record the ClinVar review status stars and the reported classification."
            
        ),
        "hht_modification": None,
        "strength_override": None,
    },

    "BP6": {
        "criterion": "BP6",
        "acmg_category": "Benign",
        "strength": "supporting",
        "automation": "fully_automatable",
        "tool": "clinvar",
        "description": (
            "Reputable source reports variant as benign. "
            "Counterpart to PP5. Same ClinVar ≥ 2-star threshold applies."
        ),
        "threshold": "ClinVar classification = Benign or Likely Benign AND review status ≥ 2 stars",
        "instructions": (
            "Search ClinVar for the variant. "
            "BP6 applies if ClinVar reports the variant as Benign or Likely Benign AND the review "
            "status is 2 or more stars. "
            "If PP5 applies (pathogenic ClinVar), BP6 cannot also apply — flag as contradictory. "
            "Record the ClinVar review status and reported classification."
        ),
        "hht_modification": None,
        "strength_override": None,
    },

    "PM4": {
        "criterion": "PM4",
        "acmg_category": "Pathogenic",
        "strength": "moderate",
        "automation": "fully_automatable",
        "tool": "vep",
        "description": (
            "Protein length change due to in-frame indel or stop-loss variant in a non-repeat region. "
            "VEP annotates consequence type and repeat region overlap."
        ),
        "threshold": "VEP consequence = inframe_insertion or inframe_deletion AND not in repeat region",
        "instructions": (
            "Use VEP to annotate the variant. "
            "PM4 applies if the variant is an in-frame insertion or deletion "
            "AND does not overlap a known repetitive region. "
            "If the variant overlaps a repeat region, PM4 does not apply — check BP3 instead."
        ),
        "hht_modification": None,
        "strength_override": None,
    },

    "BP3": {
        "criterion": "BP3",
        "acmg_category": "Benign",
        "strength": "supporting",
        "automation": "fully_automatable",
        "tool": "vep",
        "description": (
            "In-frame indel in a repetitive region without a known function. "
            "Counterpart to PM4. VEP annotates repeat region overlap."
        ),
        "threshold": "VEP consequence = inframe_insertion or inframe_deletion AND overlaps repeat region",
        "instructions": (
            "Use VEP to annotate the variant. "
            "BP3 applies if the variant is an in-frame insertion or deletion "
            "AND overlaps a known repetitive region with no known function. "
            "If PM4 applies (non-repeat region), BP3 does not apply."
        ),
        "hht_modification": None,
        "strength_override": None,
    },

    "BP1": {
        "criterion": "BP1",
        "acmg_category": "Benign",
        "strength": "supporting",
        "automation": "fully_automatable",
        "tool": "gene_lookup",
        "description": (
            "Missense variant in a gene where only truncating variants cause disease. "
            "For HHT (ENG/ACVRL1), pathogenic missense variants are well-established, "
            "so BP1 almost never applies. This is effectively a constant for HHT."
        ),
        "threshold": "BP1 applies only if gene has NO known pathogenic missense variants — for ENG/ACVRL1, BP1 = false",
        "instructions": (
            "For variants in ENG or ACVRL1: BP1 does NOT apply. "
            "Both genes have well-established pathogenic missense variants. "
            "Return applies=false with reasoning that ENG/ACVRL1 have known pathogenic missense variants. "
            "Only flag for review if the gene is not ENG or ACVRL1."
        ),
        "hht_modification": "Rarely applies for ENG/ACVRL1 — effectively a constant false",
        "strength_override": None,
    },

    # ──────────────────────────────────────────────────────────────────────────
    # PARTIALLY AUTOMATABLE — tool fetch is automatable; LLM must judge quality
    # ──────────────────────────────────────────────────────────────────────────

    "PS1": {
        "criterion": "PS1",
        "acmg_category": "Pathogenic",
        "strength": "strong",
        "automation": "partially_automatable",
        "tool": "clinvar",
        "description": (
            "Same amino acid change as a previously established pathogenic variant. "
            "ClinVar fetch is automatable. LLM must assess whether the reference variant's "
            "pathogenicity is well-established (≥2 stars, no conflicting interpretations)."
        ),
        "threshold": "Same amino acid change in ClinVar as Pathogenic with ≥2 stars and no conflicting interpretations",
        "instructions": (
            "Search ClinVar for variants producing the same amino acid change as the query variant. "
            "PS1 applies if: (1) a ClinVar entry exists with the same amino acid change, "
            "(2) the ClinVar classification is Pathogenic or Likely Pathogenic, "
            "(3) the review status is ≥2 stars, AND "
            "(4) there are no conflicting interpretations in ClinVar for that entry. "
            "LLM must explicitly assess all four conditions — do not apply PS1 if any condition fails. "
            "If ClinVar has conflicting entries for the same amino acid change, flag as uncertain "
            "and do not apply PS1."
        ),
        "hht_modification": None,
        "strength_override": None,
    },

    "PM5": {
        "criterion": "PM5",
        "acmg_category": "Pathogenic",
        "strength": "moderate",
        "automation": "partially_automatable",
        "tool": "clinvar",
        "description": (
            "Novel missense at a residue with a known pathogenic missense. "
            "HHT VCEP adds PM5_Strong for highly similar amino acid substitutions "
            "(based on Grantham score). LLM must assess ClinVar quality and calculate "
            "physicochemical similarity."
        ),
        "threshold": (
            "Different amino acid change at same residue in ClinVar as Pathogenic with ≥2 stars; "
            "PM5_Strong if Grantham score difference ≤ 60 (highly similar substitution)"
        ),
        "instructions": (
            "Search ClinVar for pathogenic variants at the same amino acid residue as the query variant "
            "(different substitution, same position). "
            "PM5 applies if: (1) a different amino acid change at the same residue is Pathogenic in ClinVar "
            "with ≥2 stars and no conflicting interpretations. "
            "If PM5 applies, calculate the Grantham score between the reference pathogenic substitution "
            "and the query substitution. If the Grantham score difference ≤ 60, upgrade to PM5_Strong. "
            "LLM must assess ClinVar review quality and Grantham score. "
            "Record the ClinVar variant found, its review status, and the Grantham score used."
        ),
        "hht_modification": "PM5_Strong added for highly similar amino acid substitutions (Grantham ≤ 60)",
        "strength_override": None,
    },

    "PM1": {
        "criterion": "PM1",
        "acmg_category": "Pathogenic",
        "strength": "moderate",
        "automation": "partially_automatable",
        "tool": "uniprot",
        "description": (
            "Variant is in a mutational hot spot or critical functional domain with no benign variation. "
            "For HHT, domain boundaries for ENG and ACVRL1 are available from UniProt and literature. "
            "Residue-level criticality may require structural knowledge."
        ),
        "threshold": "Variant residue falls within a known functional domain of ENG or ACVRL1 (UniProt domain annotations)",
        "instructions": (
            "Look up the functional domain boundaries for ENG or ACVRL1 from UniProt. "
            "PM1 applies if the variant residue falls within a known functional domain "
            "(e.g. TGF-beta receptor domain, kinase domain, orphan domain). "
            "LLM must assess whether the specific residue is within domain coordinates — "
            "hardcoded domain ranges are preferred over LLM estimation. "
            "Record which domain the residue falls in and the source of domain coordinates."
        ),
        "hht_modification": "Domain coordinates from UniProt; residue-level criticality may need structural data",
        "strength_override": None,
    },

    "PS4": {
        "criterion": "PS4",
        "acmg_category": "Pathogenic",
        "strength": "strong",
        "automation": "partially_automatable",
        "tool": "pubmed",
        "description": (
            "Variant prevalence significantly increased in affected individuals vs controls. "
            "Requires OR/RR > 5.0 or multiple unrelated cases in literature. "
            "High hallucination risk — requires careful LLM assessment of case report quality."
        ),
        "threshold": "≥2 unrelated HHT-affected individuals carrying this variant, OR/RR > 5.0; each must meet Curaçao criteria; no duplicate reports",
        "instructions": (
            "Search PubMed for case reports of this variant in HHT patients. "
            "PS4 applies only if: (1) ≥2 unrelated HHT-affected individuals carry this variant, "
            "(2) each patient meets the Curaçao diagnostic criteria for HHT "
            "(epistaxis, telangiectases, visceral lesions, family history — ≥3 criteria), "
            "(3) duplicate reports of the same patient have been excluded. "
            "LLM must explicitly evaluate all three conditions from the retrieved literature. "
            "Do not infer PS4 from ClinVar submissions — requires primary literature. "
            "If literature evidence is insufficient, return applies=false with explanation."
        ),
        "hht_modification": "Requires Curaçao criteria confirmation and deduplication of case reports",
        "strength_override": None,
    },

    # ──────────────────────────────────────────────────────────────────────────
    # NOT AUTOMATABLE — flag and defer
    # These criteria require data that no API or tool can provide.
    # The pipeline records them as deferred with an explanation.
    # ──────────────────────────────────────────────────────────────────────────

    "PS3": {
        "criterion": "PS3",
        "acmg_category": "Pathogenic",
        "strength": "strong",
        "automation": "not_automatable",
        "tool": None,
        "description": (
            "Well-established in vitro or in vivo functional studies show damaging effect. "
            "HHT VCEP requires evaluation of BMP/TGF-β signaling assays, protein expression, "
            "and RT-PCR splicing studies. Assay quality judgment required."
        ),
        "threshold": None,
        "instructions": (
            "PS3 cannot be evaluated automatically. "
            "This criterion requires reading published functional assay papers and assessing "
            "assay type, experimental design quality, and relevance to HHT disease mechanism "
            "(BMP/TGF-β signaling, protein expression, RT-PCR splicing). "
            "Strength is adjustable: PS3_Strong, PS3_Moderate, or PS3_Supporting based on assay quality. "
            "Return applies=null, status=deferred, with explanation that manual literature review is required."
        ),
        "hht_modification": "Strength adjustable; requires BMP/TGF-β signaling, protein expression, or splicing assay evidence",
        "strength_override": None,
        "deferred": True,
    },

    "BS3": {
        "criterion": "BS3",
        "acmg_category": "Benign",
        "strength": "strong",
        "automation": "not_automatable",
        "tool": None,
        "description": (
            "Well-established functional studies show no damaging effect. "
            "Counterpart to PS3. Same assay quality judgment required."
        ),
        "threshold": None,
        "instructions": (
            "BS3 cannot be evaluated automatically. "
            "Same requirements as PS3 — requires functional assay papers assessing "
            "whether the variant has no effect on BMP/TGF-β signaling, protein expression, or splicing. "
            "Return applies=null, status=deferred, with explanation that manual literature review is required."
        ),
        "hht_modification": "Strength adjustable; same assay requirements as PS3",
        "strength_override": None,
        "deferred": True,
    },

    "PP1": {
        "criterion": "PP1",
        "acmg_category": "Pathogenic",
        "strength": "supporting",
        "automation": "not_automatable",
        "tool": None,
        "description": (
            "Co-segregation with disease in affected family members. "
            "HHT VCEP uses a point-based system; phenotype must meet Curaçao Criteria. "
            "Requires confirmed family records and phase information."
        ),
        "threshold": None,
        "instructions": (
            "PP1 cannot be evaluated automatically. "
            "This criterion requires confirmed family pedigree data, phase information, "
            "and phenotype verification using the Curaçao Criteria for each family member. "
            "No genomic or population API provides this data. "
            "Return applies=null, status=deferred, with explanation."
        ),
        "hht_modification": "Point-based system; Curaçao Criteria required for each family member",
        "strength_override": None,
        "deferred": True,
    },

    "BS4": {
        "criterion": "BS4",
        "acmg_category": "Benign",
        "strength": "strong",
        "automation": "not_automatable",
        "tool": None,
        "description": (
            "Lack of segregation in affected family members. "
            "Counterpart to PP1. Same family pedigree requirements apply."
        ),
        "threshold": None,
        "instructions": (
            "BS4 cannot be evaluated automatically. "
            "Requires family pedigree data and confirmed phenotype — same as PP1. "
            "Return applies=null, status=deferred, with explanation."
        ),
        "hht_modification": None,
        "strength_override": None,
        "deferred": True,
    },

    "PP4_MODERATE": {
        "criterion": "PP4_Moderate",
        "acmg_category": "Pathogenic",
        "strength": "moderate",
        "automation": "not_automatable",
        "tool": None,
        "description": (
            "Patient phenotype highly specific for HHT and meets Curaçao Criteria (≥3 criteria). "
            "HHT VCEP created this as PP4_Moderate (upgraded from PP4_Supporting). "
            "Requires confirmed clinical records."
        ),
        "threshold": "Patient meets ≥3 of 4 Curaçao Criteria: epistaxis, telangiectases, visceral lesions, family history",
        "instructions": (
            "PP4_Moderate cannot be evaluated automatically. "
            "This criterion requires confirmed clinical records showing the patient meets "
            "≥3 of the 4 Curaçao diagnostic criteria for HHT. "
            "Curaçao Criteria: (1) spontaneous recurrent epistaxis, (2) telangiectases at "
            "characteristic sites, (3) visceral lesions, (4) first-degree relative with HHT. "
            "No genomic or population database contains this data. "
            "Return applies=null, status=deferred, with explanation."
        ),
        "hht_modification": "New HHT-specific criterion; upgraded from PP4_Supporting to PP4_Moderate",
        "strength_override": "moderate",
        "deferred": True,
    },
}

# ──────────────────────────────────────────────────────────────────────────────
# EXCLUDED CRITERIA (removed by HHT VCEP — do not classify)
# ──────────────────────────────────────────────────────────────────────────────

EXCLUDED_CRITERIA = {
    "PS2": "Removed by HHT VCEP — de novo not informative for HHT (AD disorder, de novo rare)",
    "PM6": "Removed by HHT VCEP — same rationale as PS2",
    "PM3": "Removed by HHT VCEP — AR trans mechanism not relevant; HHT is autosomal dominant",
    "BS2": "Removed by HHT VCEP — haploinsufficiency mechanism; homozygous carriers not expected",
    "BP2": "Removed by HHT VCEP — AR trans mechanism not relevant",
    "BP5": "Removed by HHT VCEP — not applicable in HHT context",
}


def query(criterion: str) -> dict | None:
    """
    Retrieves the PlanRAG entry for a given ACMG criterion.
    Returns None if no entry exists.
    Handles both exact keys (PM2_SUPPORTING) and display names (PM2_Supporting).
    When real RAG is implemented, replace the dict lookup below with vector search.
    """
    key = criterion.upper().replace("-", "_").replace(" ", "_")

    # direct lookup
    if key in PLANRAG_DB:
        return PLANRAG_DB[key]

    # partial match fallback — handles PM2 → PM2_SUPPORTING
    for db_key, entry in PLANRAG_DB.items():
        if entry["criterion"].upper().replace("_", "").replace(" ", "") == key.replace("_", "").replace(" ", ""):
            return entry

    # check if this criterion was excluded by HHT VCEP
    if key in EXCLUDED_CRITERIA:
        return {
            "criterion": criterion,
            "excluded": True,
            "reason": EXCLUDED_CRITERIA[key],
        }

    return None


def get_all_active_criteria() -> list[str]:
    """
    Returns the list of all active HHT VCEP criteria keys.
    Used by pipeline.py to build the CRITERIA list.
    """
    return list(PLANRAG_DB.keys())


def get_automatable_criteria() -> list[str]:
    """Returns only fully automatable criteria keys."""
    return [k for k, v in PLANRAG_DB.items() if v.get("automation") == "fully_automatable"]


def get_deferred_criteria() -> list[str]:
    """Returns criteria that cannot be automated."""
    return [k for k, v in PLANRAG_DB.items() if v.get("deferred", False)]