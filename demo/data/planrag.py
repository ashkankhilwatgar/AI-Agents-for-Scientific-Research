# PlanRAG database — HHT VCEP criteria for ACVRL1
# Source of truth: ClinGen CSpec Registry GN135 v1.1.0 (released 3/20/2024)
# https://cspec.genome.network/cspec/ui/svi/doc/GN135
#
# Coverage notes vs original code:
#   - PP5 and BP6 are NOT applicable per HHT VCEP (SVI Review Committee recommendation)
#     — removed from automatable list, added to EXCLUDED_CRITERIA
#   - PP2 is NOT applicable for ACVRL1 (Z-score 2.45) — moved to EXCLUDED_CRITERIA
#   - BP1 is NOT applicable for HHT (missense variants common in HHT genes)
#     — moved to EXCLUDED_CRITERIA
#   - BP3 is NOT applicable per HHT VCEP — moved to EXCLUDED_CRITERIA
#   - BP2 IS applicable per HHT VCEP (was previously in your excluded list — corrected)
#   - BP5 IS applicable per HHT VCEP for variants where pathogenic ENG variant found
#     (was previously in your excluded list — corrected)

PLANRAG_DB = {

    # ──────────────────────────────────────────────────────────────────────────
    # FULLY AUTOMATABLE
    # ──────────────────────────────────────────────────────────────────────────

    "PVS1": {
        "criterion": "PVS1",
        "acmg_category": "Pathogenic",
        "strength": "very_strong",
        "automation": "fully_automatable",
        "tool": "vep",
        "description": (
            "Null variant in ACVRL1 evaluated by the HHT VCEP PVS1 decision tree. "
            "Final strength (Very Strong / Strong / Moderate / N/A) depends on variant type, NMD prediction, "
            "and codon position. Key codon thresholds: codon 442 (NMD boundary), codon 490 (critical region boundary)."
        ),
        "threshold": "Codon 442 (NMD boundary); Codon 490 (critical region boundary)",
        "instructions": (
            "Use VEP to determine variant consequence and protein codon position. "
            "Then apply the ACVRL1 PVS1 Decision Tree (CSpec GN135 v1.1.0):\n"
            "\n"
            "NONSENSE OR FRAMESHIFT:\n"
            "  - Predicted to undergo NMD (codon <=442) → PVS1 (Very Strong)\n"
            "  - Not predicted to undergo NMD (codon >442):\n"
            "      * Truncated/altered region critical to protein function (codon <=490) → PVS1_Strong\n"
            "      * Role of region unknown AND variant removes <10% of protein → PVS1_Moderate\n"
            "\n"
            "GT-AG +/-1,2 SPLICE SITES:\n"
            "  - Exon skipping or cryptic splice disrupts reading frame, predicted NMD (codon <=442) → PVS1\n"
            "  - Exon skipping or cryptic splice disrupts reading frame, NOT predicted NMD (codon >442):\n"
            "      * Truncated/altered region critical (codon <=490, see also PM1 regions) → PVS1_Strong\n"
            "      * Role of region unknown AND variant removes <10% of protein → PVS1_Moderate\n"
            "  - Exon skipping or cryptic splice preserves reading frame:\n"
            "      * Truncated/altered region critical (codon <=490) → PVS1_Strong\n"
            "      * Role of region unknown AND variant removes <10% of protein → PVS1_Moderate\n"
            "\n"
            "DELETION (single exon to full gene):\n"
            "  - Full gene deletion → PVS1\n"
            "  - Single/multi-exon deletion disrupts reading frame, predicted NMD, exon in biologically-relevant transcript → PVS1\n"
            "  - Single/multi-exon deletion disrupts reading frame, NOT predicted NMD:\n"
            "      * Truncated/altered region critical (codon <=490) → PVS1_Strong\n"
            "      * Role of region unknown AND variant removes <10% of protein → PVS1_Moderate\n"
            "  - Single/multi-exon deletion preserves reading frame:\n"
            "      * Truncated/altered region critical (codon <=490) → PVS1_Strong\n"
            "\n"
            "DUPLICATION (>=1 exon, fully within gene):\n"
            "  - Proven in tandem AND reading frame disrupted AND NMD predicted → PVS1\n"
            "  - Proven in tandem AND no/unknown impact on reading frame and NMD → N/A\n"
            "  - Presumed in tandem AND reading frame presumed disrupted AND NMD predicted → PVS1_Strong\n"
            "  - Proven NOT in tandem → N/A\n"
            "\n"
            "INITIATION CODON:\n"
            "  - No known alternative start codon in other transcripts → PVS1_Moderate (ACVRL1)\n"
            "\n"
            "Record the variant type, codon position, NMD prediction, and final strength."
        ),
        "hht_modification": "Decision tree with codon 442 NMD boundary and codon 490 critical region boundary; initiation codon variants are PVS1_Moderate for ACVRL1",
        "strength_override": None,
    },

    "PS1": {
        "criterion": "PS1",
        "acmg_category": "Pathogenic",
        "strength": "strong",
        "automation": "partially_automatable",
        "tool": "clinvar",
        "description": (
            "Same amino acid change as a previously established pathogenic variant regardless of nucleotide change. "
            "HHT VCEP applies no modification — use as in original ACMG (Strong only). "
            "Caveat: beware of changes that impact splicing rather than at the amino acid/protein level. "
            "ClinVar fetch is automatable; LLM must assess whether the reference variant's pathogenicity "
            "is well-established (>=2 stars, no conflicting interpretations)."
        ),
        "threshold": "Same amino acid change in ClinVar as Pathogenic with >=2 stars and no conflicting interpretations",
        "instructions": (
            "Search ClinVar for variants at the same amino acid position producing the same amino acid change\n"
            "as the query variant, regardless of nucleotide change.\n"
            "\n"
            "STEP 1: Does a ClinVar entry exist with the same amino acid change?\n"
            "  - NO  → PS1 does NOT apply. Set applies=false. Stop.\n"
            "  - YES → continue to Step 2.\n"
            "\n"
            "STEP 2: Is the ClinVar classification Pathogenic or Likely Pathogenic?\n"
            "  - NO  → PS1 does NOT apply. Set applies=false. Stop.\n"
            "  - YES → continue to Step 3.\n"
            "\n"
            "STEP 3: Is the ClinVar review status 2 stars or higher?\n"
            "  - NO  → PS1 does NOT apply. Set applies=false. Stop.\n"
            "  - YES → continue to Step 4.\n"
            "\n"
            "STEP 4: Are there any conflicting interpretations in ClinVar?\n"
            "  - YES → PS1 does NOT apply. Set applies=false. Stop.\n"
            "  - NO  → continue to Step 5.\n"
            "\n"
            "STEP 5: Could the query variant affect splicing rather than the amino acid change?\n"
            "  - YES → PS1 is NOT appropriate. Set applies=false.\n"
            "  - NO  → PS1 APPLIES. Set applies=true. Strength is Strong only.\n"
            "\n"
            "ALL five steps must pass for PS1 to apply. Failing any single step means applies=false.\n"
            "Record the ClinVar variant ID, classification, star rating, and amino acid change in evidence."
        ),
        "hht_modification": "No modification — use as in original ACMG; Strong strength only",
        "strength_override": "strong",
    },

    "PS3": {
        "criterion": "PS3",
        "acmg_category": "Pathogenic",
        "strength": "strong",
        "automation": "not_automatable",
        "tool": None,
        "description": (
            "Well-established in vitro or in vivo functional studies supportive of a damaging effect. "
            "HHT VCEP defines three strength levels: "
            "Strong — mRNA splicing assays (do not use PS3 for splice variants that meet PVS1); "
            "Moderate — see Supporting + concordant multiple assays; "
            "Supporting — protein expression assays (WB & FACS HUVECs/BOECs, FACS activated monocytes, "
            "cDNA transfect WB & ML in HEK293T/COS/NIH3T3, luciferase HepG2), "
            "intracellular signaling assays (BRE/CAGA-luciferase, Gal4 Smad1/Smad3 for TGF-beta/BMP9 signaling), "
            "binding assays (BMP9 binding, Sp1, BLI), subcellular localization, morphology (actin cytoskeleton, "
            "tubulogenesis), or somatic 2nd-hit evidence. "
            "Strength can be bumped up to Moderate/Strong if multiple different assays are concordant."
        ),
        "threshold": None,
        "instructions": (
            "PS3 cannot be evaluated automatically. "
            "Requires reading published functional assay papers and assessing assay type and quality. "
            "Strength levels per HHT VCEP: "
            "STRONG — mRNA splicing assays only (and not for splice variants already meeting PVS1); "
            "MODERATE — multiple concordant assays from the Supporting list; "
            "SUPPORTING — single assay from: protein expression, intracellular signaling (BMP9/TGF-beta), "
            "binding, subcellular localization, morphology, or somatic 2nd-hit (PMID: 31630786). "
            "Note for protein expression assays: decreased expression is acceptable Supporting evidence only "
            "if experiment was not done in a single assay AND densitometry of WB reflects the conclusion. "
            "Return applies=null, status=deferred, with explanation that manual literature review is required."
        ),
        "hht_modification": "Three strength levels: Strong (splicing), Moderate (concordant multiple assays), Supporting (single assay from defined list); do not use PS3 for splice variants meeting PVS1",
        "strength_override": None,
        "deferred": True,
    },

    "PS4": {
        "criterion": "PS4",
        "acmg_category": "Pathogenic",
        "strength": "strong",
        "automation": "partially_automatable",
        "tool": "pubmed",
        "description": (
            "Prevalence of variant in affected individuals significantly increased vs controls. "
            "HHT VCEP uses proband counting (not OR/RR) with three strength levels: "
            "Strong = 4+ probands; Moderate = 2-3 probands; Supporting = 1 proband. "
            "Variant must also meet PM2_Supporting. "
            "Phenotype must be consistent with HHT (see HHT phenotype document). "
            "Note: probands meeting PP4_Moderate cannot also be counted for PS4."
        ),
        "threshold": "PS4_Strong: 4+ probands; PS4_Moderate: 2-3 probands; PS4_Supporting: 1 proband; variant must also meet PM2_Supporting",
        "instructions": (
            "Search PubMed and ClinVar for case reports of this variant in HHT patients.\n"
            "\n"
            "STEP 1: Does the variant meet PM2_Supporting (absent or very rare in gnomAD)?\n"
            "  - NO  → PS4 does NOT apply. Set applies=false. Stop.\n"
            "  - YES → continue to Step 2.\n"
            "\n"
            "STEP 2: Count unrelated probands with phenotype consistent with HHT.\n"
            "  Rules for counting:\n"
            "    - Each proband must have phenotype consistent with HHT.\n"
            "    - Exclude duplicate reports of the same patient across papers.\n"
            "    - Do NOT count probands who qualify for PP4_Moderate — those are counted only under PP4_Moderate.\n"
            "\n"
            "STEP 3: Apply strength based on proband count:\n"
            "  - Count >= 4 → PS4_Strong applies. Set applies=true, strength=strong.\n"
            "  - Count = 2 or 3 → PS4_Moderate applies. Set applies=true, strength=moderate.\n"
            "  - Count = 1 → PS4_Supporting applies. Set applies=true, strength=supporting.\n"
            "  - Count = 0 → PS4 does NOT apply. Set applies=false.\n"
            "\n"
            "Record proband count, references, and strength level in evidence."
        ),
        "hht_modification": "Proband-based counting (4+ Strong / 2-3 Moderate / 1 Supporting); requires PM2_Supporting; PP4_Moderate probands excluded from count",
        "strength_override": None,
    },

    "PM1": {
        "criterion": "PM1",
        "acmg_category": "Pathogenic",
        "strength": "moderate",
        "automation": "fully_automatable",
        "tool": "uniprot",
        "description": (
            "Variant located in a critical residue of ACVRL1. "
            "HHT VCEP defines specific critical residues based on functional and structural data: "
            "glycine-rich loop (G209-V216), phosphate anchor (K229), C-helix E pairing the phosphate anchor (E242), "
            "catalytic loop (R329-N335), metal-binding loop (D348-L351), and the BMP10 interaction cluster "
            "(His40, Val54, Val56, Arg57, Glu58, Glu59, His66, Asn71, Leu72, His73, Glu75, Leu76, Arg78, Gly79, "
            "Arg80, Thr82, Glu83, Phe84, Val85, His87). "
            "PM1 applies only at Moderate strength. "
            "If variant falls within a PM1 region, do not use PM1 with PM5_Strong; PM1 + PM5 (Moderate) is allowed."
        ),
        "threshold": "Variant residue is in: G209-V216 OR K229 OR E242 OR R329-N335 OR D348-L351 OR BMP10 cluster {40,54,56,57,58,59,66,71,72,73,75,76,78,79,80,82,83,84,85,87}",
        "instructions": (
            "Determine the protein position of the variant on ACVRL1 (NM_000020.3). "
            "PM1_Moderate applies if the residue is in ANY of these critical regions: "
            "(1) glycine-rich loop: positions 209-216 inclusive; "
            "(2) phosphate anchor: position 229; "
            "(3) C-helix E pairing the phosphate anchor: position 242; "
            "(4) catalytic loop: positions 329-335 inclusive; "
            "(5) metal-binding loop: positions 348-351 inclusive; "
            "(6) BMP10 interaction cluster: positions 40, 54, 56, 57, 58, 59, 66, 71, 72, 73, 75, 76, 78, 79, 80, 82, 83, 84, 85, 87. "
            "This is a hardcoded residue list — no UniProt lookup needed, no LLM judgment needed. "
            "RULE: if PM1 applies, do NOT combine with PM5_Strong. PM1 + PM5 (Moderate) IS allowed."
        ),
        "hht_modification": "Hardcoded critical residue list per CSpec GN135 v1.1.0; Moderate strength only; cannot combine with PM5_Strong",
        "strength_override": "moderate",
    },

    "PM2_SUPPORTING": {
        "criterion": "PM2_Supporting",
        "acmg_category": "Pathogenic",
        "strength": "supporting",
        "automation": "fully_automatable",
        "tool": "gnomad",
        "description": (
            "Variant absent or at extremely low frequency in population databases. "
            "HHT VCEP defines PM2 at Supporting strength only with the threshold: "
            "<6 total alleles in gnomAD OR <0.00004 (0.004%) in gnomAD subpopulations."
        ),
        "threshold": "<6 total alleles in gnomAD OR <0.00004 (0.004%) in any gnomAD subpopulation",
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
    },

    "PM4": {
        "criterion": "PM4",
        "acmg_category": "Pathogenic",
        "strength": "moderate",
        "automation": "fully_automatable",
        "tool": "vep",
        "description": (
            "Protein length changes due to in-frame deletions/insertions in a non-repeat region or stop-loss variants. "
            "HHT VCEP: no modification, use as applicable. Moderate strength only."
        ),
        "threshold": "VEP consequence = inframe_insertion, inframe_deletion, or stop_lost; not in repeat region",
        "instructions": (
            "Use VEP to annotate the variant consequence.\n"
            "\n"
            "STEP 1: What is the VEP consequence?\n"
            "  - inframe_insertion → continue to Step 2.\n"
            "  - inframe_deletion  → continue to Step 2.\n"
            "  - stop_lost         → PM4_Moderate APPLIES. Set applies=true. Stop.\n"
            "  - anything else     → PM4 does NOT apply. Set applies=false. Stop.\n"
            "\n"
            "STEP 2 (in-frame indels only): Does the variant overlap a repeat region?\n"
            "  - true → PM4 does NOT apply. Set applies=false.\n"
            "  - false → PM4_Moderate APPLIES. Set applies=true.\n"
            "\n"
            "Record VEP consequence and repeat region status in evidence."
        ),
        "hht_modification": "No modification — use as in original ACMG",
        "strength_override": "moderate",
    },

    "PM5": {
        "criterion": "PM5",
        "acmg_category": "Pathogenic",
        "strength": "moderate",
        "automation": "partially_automatable",
        "tool": "clinvar",
        "description": (
            "Novel missense at an amino acid residue where a different missense change has been determined "
            "to be likely pathogenic or pathogenic based on HHT VCEP rules. "
            "HHT VCEP defines two strength levels: "
            "Strong — >=2 different missense changes at same codon classified LP/P by HHT VCEP rules; "
            "Moderate — 1 different missense change at same codon classified LP/P by HHT VCEP rules. "
            "Important: reference variants must be classified per HHT VCEP rules, not just any ClinVar submission. "
            "Cannot combine PM5_Strong with PM1 (PM5_Moderate + PM1 IS allowed)."
        ),
        "threshold": "PM5_Strong: >=2 different LP/P missense (HHT VCEP rules) at same codon; PM5_Moderate: 1 different LP/P missense (HHT VCEP rules) at same codon",
        "instructions": (
            "primary_source: ClinGen Evidence Repository (https://erepo.clinicalgenome.org); "
            "fallback_source: ClinVar entries with submitter = 'ClinGen Hereditary Hemorrhagic Telangiectasia VCEP'; "
            "search_strategy: Find variants at same amino acid residue, different substitution; "
            "filter: Only count variants classified LP or P by HHT VCEP; "
            "note: These are pipeline-level decisions, not from CSpec GN135 v1.1.0; "
            "Apply strength: PM5_Strong if >=2 different missense changes at same codon are LP/P per HHT VCEP rules; "
            "PM5_Moderate if 1 different missense change at same codon is LP/P per HHT VCEP rules. "
            "Caveat: beware of changes that impact splicing rather than at the amino acid/protein level. "
            "RULE: do not combine PM5_Strong with PM1. PM5_Moderate + PM1 IS allowed."
        ),
        "hht_modification": "Two strength levels (Strong / Moderate) based on count of LP/P missense at same codon; reference must be HHT VCEP-classified; PM5_Strong cannot combine with PM1",
        "strength_override": None,
    },

    "PP1": {
        "criterion": "PP1",
        "acmg_category": "Pathogenic",
        "strength": "supporting",
        "automation": "not_automatable",
        "tool": None,
        "description": (
            "Co-segregation with disease in multiple affected family members. "
            "HHT VCEP uses meiosis-based scoring: "
            "Strong — 5+ meioses (1/32 likelihood); "
            "Moderate — 4 meioses (1/16 likelihood); "
            "Supporting — 3 meioses (1/8 likelihood). "
            "Affected/unaffected status must be assigned per the HHT phenotype document."
        ),
        "threshold": "PP1_Strong: 5+ meioses; PP1_Moderate: 4 meioses; PP1_Supporting: 3 meioses",
        "instructions": (
            "PP1 cannot be evaluated automatically. "
            "Requires confirmed family pedigree with affected/unaffected status assigned per HHT phenotype document. "
            "Count informative meioses (transmissions of the variant tracked with phenotype). "
            "Strength: PP1_Strong = 5+ meioses, PP1_Moderate = 4 meioses, PP1_Supporting = 3 meioses. "
            "Return applies=null, status=deferred, with explanation."
        ),
        "hht_modification": "Meiosis-based scoring (5+/4/3 meioses for Strong/Moderate/Supporting)",
        "strength_override": None,
        "deferred": True,
    },

    "PP3": {
        "criterion": "PP3",
        "acmg_category": "Pathogenic",
        "strength": "supporting",
        "automation": "fully_automatable",
        "tool": "revel_spliceai",
        "variant_types": ["missense", "synonymous", "intronic"],
        "description": (
            "Multiple lines of computational evidence support a deleterious effect. "
            "HHT VCEP specifies thresholds at Supporting strength only: "
            "For missense variants — REVEL >=0.644 OR SpliceAI >=0.2; "
            "For synonymous and intronic variants — SpliceAI >=0.2."
        ),
        "threshold": "Missense: REVEL >=0.644 OR SpliceAI >=0.2 | Synonymous/intronic: SpliceAI >=0.2",
        "instructions": (
            "Fetch REVEL score and all four SpliceAI delta scores (DS_AG, DS_AL, DS_DG, DS_DL).\n"
            "PP3 can be used only once per variant evaluation.\n"
            "\n"
            "BRANCH A — Missense variant:\n"
            "  STEP 1: Is REVEL score >= 0.644?\n"
            "    - YES → PP3 APPLIES. Set applies=true. Stop. Record REVEL score as trigger.\n"
            "    - NO  → continue to Step 2.\n"
            "  STEP 2: Is ANY SpliceAI delta score (DS_AG, DS_AL, DS_DG, DS_DL) >= 0.2?\n"
            "    - YES → PP3 APPLIES. Set applies=true. Stop. Record which score triggered.\n"
            "    - NO  → PP3 does NOT apply. Set applies=false.\n"
            "\n"
            "BRANCH B — Synonymous or intronic variant:\n"
            "  STEP 1: Is ANY SpliceAI delta score (DS_AG, DS_AL, DS_DG, DS_DL) >= 0.2?\n"
            "    - YES → PP3 APPLIES. Set applies=true. Record which score triggered.\n"
            "    - NO  → PP3 does NOT apply. Set applies=false.\n"
            "\n"
            "IMPORTANT: For missense, REVEL and SpliceAI are independent triggers — either one alone is sufficient (OR logic).\n"
            "Record exact scores and which threshold triggered in the evidence field."
        ),
        "hht_modification": "Supporting strength only; thresholds: REVEL >=0.644 (missense); SpliceAI >=0.2 (any variant type)",
        "strength_override": "supporting",
    },

    "PP4_MODERATE": {
        "criterion": "PP4_Moderate",
        "acmg_category": "Pathogenic",
        "strength": "moderate",
        "automation": "not_automatable",
        "tool": None,
        "description": (
            "Patient's phenotype meets consensus clinical diagnostic (Curaçao) criteria for HHT, AND "
            "sequencing and large deletion/duplication analysis was performed for both ENG and ACVRL1 "
            "with any other identified variants ruled out. "
            "HHT VCEP applies PP4 at Moderate strength only. "
            "RULES: PP4_Moderate cannot be applied to variants meeting BS1_Supporting, BS1, or BA1. "
            "Patients counted for PP4_Moderate cannot be counted in PS4 proband counting."
        ),
        "threshold": "Patient meets Curaçao Criteria (>=3 of 4: epistaxis, telangiectases, visceral lesions, family history) AND comprehensive ENG/ACVRL1 sequencing + del/dup analysis ruled out other variants",
        "instructions": (
            "PP4_Moderate cannot be evaluated automatically. "
            "Requires confirmed clinical records showing: "
            "(1) patient meets Curaçao Criteria (>=3 of 4: spontaneous recurrent epistaxis, "
            "telangiectases at characteristic sites, visceral lesions, first-degree relative with HHT), AND "
            "(2) comprehensive sequencing and large deletion/duplication analysis was performed for BOTH "
            "ENG and ACVRL1, with all other identified variants ruled out. "
            "BLOCKED IF: variant meets BS1_Supporting, BS1, or BA1 — PP4_Moderate cannot apply in those cases. "
            "If PP4_Moderate applies to a patient, that patient cannot be counted in PS4 proband counting. "
            "Return applies=null, status=deferred, with explanation."
        ),
        "hht_modification": "Moderate strength only; requires Curaçao Criteria AND comprehensive ENG/ACVRL1 testing; blocked by BS1_Supporting/BS1/BA1; mutually exclusive with PS4 counting",
        "strength_override": "moderate",
        "deferred": True,
    },

    "BA1": {
        "criterion": "BA1",
        "acmg_category": "Benign",
        "strength": "stand_alone",
        "automation": "fully_automatable",
        "tool": "gnomad",
        "description": (
            "Allele frequency is high enough for stand-alone benign classification. "
            "HHT VCEP defines BA1 as: Popmax FAF >=1% (0.01) in gnomAD. "
            "If BA1 applies, PP4_Moderate cannot also be applied."
        ),
        "threshold": "Popmax FAF >= 0.01 (1%) in gnomAD",
        "instructions": (
            "Query gnomAD for the Popmax Filtering Allele Frequency (FAF95, popmax field).\n"
            "\n"
            "STEP 1: Is Popmax FAF greater than or equal to 0.01 (i.e. >= 1%)?\n"
            "  - Popmax FAF >= 0.01 → BA1 APPLIES. Set applies=true.\n"
            "    This is stand-alone benign — variant is classified Benign regardless of all other evidence.\n"
            "    PP4_Moderate cannot be applied if BA1 applies.\n"
            "  - Popmax FAF < 0.01  → BA1 does NOT apply. Set applies=false.\n"
            "  - Variant absent from gnomAD (popmax_faf = 0 or null) → BA1 does NOT apply. Set applies=false.\n"
            "\n"
            "IMPORTANT: BA1 applies only when Popmax FAF is HIGH (>= 1%). A low frequency means BA1 does NOT apply.\n"
            "Record exact Popmax FAF value in evidence."
        ),
        "hht_modification": "Popmax FAF >=0.01 (1%) in gnomAD; blocks PP4_Moderate",
        "strength_override": "stand_alone",
    },

    "BS1": {
        "criterion": "BS1",
        "acmg_category": "Benign",
        "strength": "strong",
        "automation": "fully_automatable",
        "tool": "gnomad",
        "description": (
            "Allele frequency is greater than expected for the disorder. "
            "HHT VCEP defines two strength levels using Popmax FAF (bottlenecked populations included):(e.g. Ashkenazi Jewish). The HHT VCEP does not exclude these from the frequency threshold calculation"
            "Strong — Popmax FAF >0.2% to <1% (i.e. >0.002 and <0.01), OR variant meets BS1_Supporting AND has >=2 homozygotes; "
            "Supporting — Popmax FAF >0.08% to 0.2% (i.e. >0.0008 and <=0.002). "
            "If BS1 or BS1_Supporting applies, PP4_Moderate cannot also be applied."
        ),
        "threshold": "BS1_Strong: Popmax FAF >0.002 and <0.01 (OR BS1_Supporting + >=2 homozygotes); BS1_Supporting: Popmax FAF >0.0008 and <=0.002",
        "instructions": (
            "Query gnomAD for Popmax FAF (faf95 popmax field) and total homozygote count (ac_hom).\n"
            "Bottlenecked populations (e.g. Ashkenazi Jewish) are included — do not exclude them.\n"
            "\n"
            "STEP 1: Does BA1 already apply (Popmax FAF >= 0.01)?\n"
            "  - YES → do NOT apply BS1. BA1 supersedes it. Set applies=false. Stop.\n"
            "  - NO  → continue to Step 2.\n"
            "\n"
            "STEP 2: Check for BS1_Strong via the homozygote route.\n"
            "  Is Popmax FAF > 0.0008 AND <= 0.002 (i.e. BS1_Supporting range) AND homozygote count >= 2?\n"
            "  - YES → BS1_Strong APPLIES via homozygote route. Set applies=true, strength=strong. Stop.\n"
            "  - NO  → continue to Step 3.\n"
            "\n"
            "STEP 3: Check for BS1_Strong via the FAF route.\n"
            "  Is Popmax FAF > 0.002 AND < 0.01?\n"
            "  - YES → BS1_Strong APPLIES. Set applies=true, strength=strong. Stop.\n"
            "  - NO  → continue to Step 4.\n"
            "\n"
            "STEP 4: Check for BS1_Supporting.\n"
            "  Is Popmax FAF > 0.0008 AND <= 0.002?\n"
            "  - YES → BS1_Supporting APPLIES. Set applies=true, strength=supporting. Stop.\n"
            "  - NO  → BS1 does NOT apply. Set applies=false.\n"
            "\n"
            "NOTE: If BS1 or BS1_Supporting applies, PP4_Moderate cannot be applied.\n"
            "Record exact Popmax FAF, homozygote count, and which strength level triggered."
        ),
        "hht_modification": "Two strength levels (Strong: >0.2-<1% OR BS1_Sup + 2 homozygotes; Supporting: >0.08-0.2%); Popmax FAF including bottlenecked populations; blocks PP4_Moderate",
        "strength_override": None,
    },

    "BS3": {
        "criterion": "BS3",
        "acmg_category": "Benign",
        "strength": "supporting",
        "automation": "not_automatable",
        "tool": None,
        "description": (
            "Well-established functional studies show no damaging effect on protein function or splicing. "
            "HHT VCEP applies BS3 at Supporting strength only. "
            "Acceptable assays: mRNA splicing assays, intracellular signaling (BRE/CAGA-luciferase, "
            "Gal4 Smad1/Smad3 for TGF-beta/BMP9), binding assays (BMP9, Sp1, BLI), subcellular protein "
            "localization, morphology (actin cytoskeleton, tubulogenesis). "
            "IMPORTANT: Normal protein expression alone CANNOT be used as benign evidence — protein function "
            "can still be altered (e.g. dominant negative variants)."
        ),
        "threshold": None,
        "instructions": (
            "BS3 cannot be evaluated automatically. "
            "Requires reading published functional assay papers. "
            "Strength is Supporting only per HHT VCEP. "
            "Acceptable assays: mRNA splicing, intracellular signaling (BMP9/TGF-beta), binding, "
            "subcellular localization, morphology. "
            "EXCLUSION: normal protein expression alone is NOT acceptable as benign evidence. "
            "Return applies=null, status=deferred, with explanation."
        ),
        "hht_modification": "Supporting strength only; normal protein expression alone NOT acceptable as benign evidence",
        "strength_override": "supporting",
        "deferred": True,
    },

    "BS4": {
        "criterion": "BS4",
        "acmg_category": "Benign",
        "strength": "strong",
        "automation": "not_automatable",
        "tool": None,
        "description": (
            "Lack of segregation in affected members of a family. "
            "HHT VCEP applies BS4 at Strong strength only. "
            "Affected/unaffected status must be assigned per the HHT phenotype document. "
            "Caveat: presence of phenocopies and the possibility of multiple pathogenic variants in one "
            "family can mimic lack of segregation."
        ),
        "threshold": "Lack of segregation in affected family members (affected/unaffected status per HHT phenotype document)",
        "instructions": (
            "BS4 cannot be evaluated automatically. "
            "Requires family pedigree data with affected/unaffected status assigned per HHT phenotype document. "
            "Consider phenocopies and possibility of additional pathogenic variants in the family. "
            "Return applies=null, status=deferred, with explanation."
        ),
        "hht_modification": "Strong strength only; affected/unaffected status per HHT phenotype document",
        "strength_override": "strong",
        "deferred": True,
    },

    "BP2": {
        "criterion": "BP2",
        "acmg_category": "Benign",
        "strength": "supporting",
        "automation": "partially_automatable",
        "tool": "clinvar",
        "description": (
            "Observed in trans with a pathogenic or likely pathogenic variant (per HHT VCEP rules). "
            "HHT VCEP applies BP2 at Supporting strength only. "
            "REQUIREMENT: variants must be confirmed in trans (phase confirmed)."
        ),
        "threshold": "Confirmed in trans with a P/LP variant classified per HHT VCEP rules",
        "instructions": (
            "BP2 applies if the variant is observed in trans with a Pathogenic or Likely Pathogenic variant "
            "classified per HHT VCEP rules. "
            "Phase MUST be confirmed (parental testing or read-based phasing) — assumed in trans is not sufficient. "
            "Search ClinVar / literature for co-occurring P/LP variants in HHT VCEP-classified entries. "
            "Note: HHT is autosomal dominant; BP2 in trans suggests this variant is unlikely to be pathogenic "
            "because the patient would otherwise have biallelic LOF, which is generally embryonic lethal in HHT genes. "
            "Return applies=null, status=deferred if phase cannot be confirmed."
        ),
        "hht_modification": "Supporting strength only; phase must be confirmed; reference variant must be HHT VCEP-classified P/LP",
        "strength_override": "supporting",
    },

    "BP4": {
        "criterion": "BP4",
        "acmg_category": "Benign",
        "strength": "supporting",
        "automation": "fully_automatable",
        "tool": "revel_spliceai",
        "variant_types": ["missense", "synonymous", "intronic"],
        "description": (
            "Multiple lines of computational evidence suggest no impact on gene product. "
            "HHT VCEP thresholds at Supporting strength only: "
            "For missense variants — REVEL <=0.15 AND SpliceAI <=0.1 (BOTH required); "
            "For synonymous and intronic variants — SpliceAI <=0.1. "
            "BP4 can be used only once per variant evaluation."
        ),
        "threshold": "Missense: REVEL <=0.15 AND SpliceAI <=0.1 | Synonymous/intronic: SpliceAI <=0.1",
        "instructions": (
            "Fetch REVEL score and all four SpliceAI delta scores (DS_AG, DS_AL, DS_DG, DS_DL).\n"
            "BP4 can be used only once per variant evaluation.\n"
            "\n"
            "BRANCH A — Missense variant (BOTH conditions must be true — AND logic):\n"
            "  STEP 1: Is REVEL score <= 0.15?\n"
            "    - NO  → BP4 does NOT apply. Set applies=false. Stop.\n"
            "    - YES → continue to Step 2.\n"
            "  STEP 2: Are ALL four SpliceAI delta scores (DS_AG, DS_AL, DS_DG, DS_DL) <= 0.1?\n"
            "    - NO  (any score > 0.1) → BP4 does NOT apply. Set applies=false. Stop.\n"
            "    - YES (all scores <= 0.1) → BP4 APPLIES. Set applies=true.\n"
            "\n"
            "BRANCH B — Synonymous or intronic variant (SpliceAI only):\n"
            "  STEP 1: Are ALL four SpliceAI delta scores (DS_AG, DS_AL, DS_DG, DS_DL) <= 0.1?\n"
            "    - NO  (any score > 0.1) → BP4 does NOT apply. Set applies=false.\n"
            "    - YES (all scores <= 0.1) → BP4 APPLIES. Set applies=true.\n"
            "\n"
            "IMPORTANT: For missense, failing EITHER condition means BP4 does NOT apply (AND logic, not OR).\n"
            "Record exact REVEL and SpliceAI scores in evidence."
        ),
        "hht_modification": "Missense requires BOTH REVEL <=0.15 AND SpliceAI <=0.1 (not OR); synonymous/intronic uses SpliceAI <=0.1 only",
        "strength_override": "supporting",
    },

    "BP5": {
        "criterion": "BP5",
        "acmg_category": "Benign",
        "strength": "supporting",
        "automation": "partially_automatable",
        "tool": "clinvar",
        "description": (
            "Variant found in a case with an alternate molecular basis for disease. "
            "HHT VCEP applies BP5 at Supporting strength when: a likely pathogenic or pathogenic variant "
            "(per HHT VCEP rules) is identified in ENG. "
            "Rationale: this is ACVRL1-specific spec — if the patient's HHT is explained by a P/LP ENG variant, "
            "an ACVRL1 variant in the same patient is less likely to be the cause."
        ),
        "threshold": "Patient also carries a P/LP variant in ENG (per HHT VCEP rules)",
        "instructions": (
            "BP5 applies if a likely pathogenic or pathogenic variant in ENG (per HHT VCEP rules) "
            "is identified in the same patient. "
            "This requires patient-level data — search ClinVar / literature for co-reported ENG variants "
            "and check whether they are classified P/LP by the HHT VCEP. "
            "Return applies=null, status=deferred if patient-level data is not available."
        ),
        "hht_modification": "Supporting strength only; specifically applies when a P/LP ENG variant (HHT VCEP rules) is found in the same patient",
        "strength_override": "supporting",
    },

    "BP7": {
        "criterion": "BP7",
        "acmg_category": "Benign",
        "strength": "supporting",
        "automation": "fully_automatable",
        "tool": "spliceai",
        "variant_types": ["synonymous", "intronic"],
        "description": (
            "Synonymous or intronic variant with no predicted splice impact. "
            "HHT VCEP threshold: SpliceAI <=0.1 at Supporting strength. "
            "Can be combined with BP4 evidence. "
            "CAUTION per HHT VCEP: do not dismiss intronic or last-nucleotide-of-exon synonymous variants "
            "based on SpliceAI alone when clinical suspicion is high (some validated splice variants have "
            "low SpliceAI scores — see ENG c.219G>A example and ACVRL1 intron 9 CT-rich hotspot)."
        ),
        "threshold": "Synonymous or intronic variant AND SpliceAI <=0.1",
        "instructions": (
            "Fetch all four SpliceAI delta scores (DS_AG, DS_AL, DS_DG, DS_DL).\n"
            "BP7 applies to synonymous or intronic variants only — not missense.\n"
            "\n"
            "STEP 1: Are ALL four SpliceAI delta scores <= 0.1?\n"
            "  - YES (all four <= 0.1) → BP7 APPLIES. Set applies=true.\n"
            "  - NO  (any score > 0.1) → BP7 does NOT apply. Set applies=false.\n"
            "\n"
            "CAUTION: Even if BP7 applies, flag the following for manual review:\n"
            "  - Variant at the last nucleotide of an exon\n"
            "  - Deep intronic variant in a known splicing hotspot (e.g. ACVRL1 intron 9 CT-rich region)\n"
            "  SpliceAI can miss real splice effects in these regions.\n"
            "\n"
            "Record all four SpliceAI scores in evidence."
        ),
        "hht_modification": "Supporting strength; SpliceAI <=0.1; flag last-exon-nucleotide and deep intronic hotspot variants for manual review even if SpliceAI is low",
        "strength_override": "supporting",
    },
}


# ──────────────────────────────────────────────────────────────────────────────
# EXCLUDED CRITERIA — Not Applicable per HHT VCEP CSpec GN135 v1.1.0
# ──────────────────────────────────────────────────────────────────────────────

EXCLUDED_CRITERIA = {
    "PS2": "Not Applicable per HHT VCEP — de novo variants are rare in HHT; should be confirmed not presumed. Low-level mosaicism in parents has been observed.",
    "PM3": "Not Applicable per HHT VCEP — HHT is autosomal dominant; AR trans mechanism not relevant",
    "PM6": "Not Applicable per HHT VCEP — de novo variants are rare in HHT; should be confirmed not presumed",
    "PP2": "Not Applicable for ACVRL1 — gene missense Z-score is 2.45 (below threshold for PP2)",
    "PP5": "Not Applicable per ClinGen SVI VCEP Review Committee (PMID: 29543229)",
    "BS2": "Not Applicable per HHT VCEP — full penetrance at an early age is not observed in HHT",
    "BP1": "Not Applicable per HHT VCEP — missense variants commonly seen in HHT genes",
    "BP3": "Not Applicable per HHT VCEP",
    "BP6": "Not Applicable per ClinGen SVI VCEP Review Committee (PMID: 29543229)",
}


def query(criterion: str) -> dict | None:
    """
    Retrieve the PlanRAG entry for a given ACMG criterion.
    Returns None if no entry exists.
    Handles both exact keys (PM2_SUPPORTING) and display names (PM2_Supporting).
    """
    key = criterion.upper().replace("-", "_").replace(" ", "_")

    if key in PLANRAG_DB:
        return PLANRAG_DB[key]

    for db_key, entry in PLANRAG_DB.items():
        if entry["criterion"].upper().replace("_", "").replace(" ", "") == key.replace("_", "").replace(" ", ""):
            return entry

    if key in EXCLUDED_CRITERIA:
        return {
            "criterion": criterion,
            "excluded": True,
            "reason": EXCLUDED_CRITERIA[key],
        }

    return None


def get_all_active_criteria() -> list[str]:
    """List of all active HHT VCEP criteria keys."""
    return list(PLANRAG_DB.keys())


def get_automatable_criteria() -> list[str]:
    """Fully automatable criteria keys."""
    return [k for k, v in PLANRAG_DB.items() if v.get("automation") == "fully_automatable"]


def get_deferred_criteria() -> list[str]:
    """Criteria that cannot be automated."""
    return [k for k, v in PLANRAG_DB.items() if v.get("deferred", False)]