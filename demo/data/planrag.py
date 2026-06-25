# PlanRAG database — HHT VCEP criteria for ACVRL1 and ENG
# Sources of truth:
#   GN135 v1.1.0 (released 3/20/2024) — ACVRL1/HHT
#     https://cspec.genome.network/cspec/ui/svi/doc/GN135
#   GN136 v1.1.0 (released 3/20/2024) — ENG/HHT
#     https://cspec.genome.network/cspec/ui/svi/doc/GN136
#
# Gene-specific branches exist for PM1 and PVS1 only.
# All other criteria are identical between ACVRL1 and ENG.
#
# EXECUTION ORDER:
#   Phase 1: PM2_Supporting, BA1, BS1 (gnomAD — no dependencies, others depend on these)
#   Phase 2: PS4 (needs PM2), PP4_Moderate (blocked by BA1/BS1), PM1 (needed before PM5)
#   Phase 3: PVS1 (needed before PS3), PM5 (needs PM1), PS3 (needs PVS1 for splice exclusion)
#   Phase 4: PS1, PP3, BP4, BP7, PM4, PP1, BS3, BS4, BP2, BP5 (no dependencies)
#
# Dependencies:
#   PS4 requires PM2_Supporting
#   PP4_Moderate blocked by BA1 / BS1 / BS1_Supporting
#   PM5_Strong cannot combine with PM1
#   PS3 cannot apply to splice variants that meet PVS1
#
# Coverage notes:
#   - PP5 and BP6 are NOT applicable per HHT VCEP (SVI Review Committee recommendation)
#   - BP1 is NOT applicable for HHT (missense variants common in HHT genes)
#   - BP3 is NOT applicable per HHT VCEP
#   - BP2 IS applicable per HHT VCEP (confirmed in trans)
#   - BP5 IS applicable per HHT VCEP; gene-specific: references the other HHT gene

# ──────────────────────────────────────────────────────────────────────────────
# GENE REGISTRY — transcript → gene symbol mapping + metadata
# ──────────────────────────────────────────────────────────────────────────────

GENE_DB = {
    "ACVRL1": {
        "gene_symbol":    "ACVRL1",
        "transcripts":    ["NM_000020"],        # NM_000020.x (any version)
        "protein_length": 503,                  # aa
        "total_exons":    10,
        "cspec_id":       "GN135",
        # LOF mechanism — used by PVS1 prerequisite check
        "lof_mechanism":       True,
        "lof_mechanism_note":  "ACVRL1 causes HHT type 2 via haploinsufficiency; frameshift, nonsense, and splice variants are well-established pathogenic mechanisms.",
    },
    "ENG": {
        "gene_symbol":    "ENG",
        "transcripts":    ["NM_001114753", "NM_000118", "NM_001278138"],   # NM_001114753.x, NM_000118.x, NM_001278138.x
        "protein_length": 658,                  # aa
        "total_exons":    15,
        "cspec_id":       "GN136",
        # LOF mechanism — used by PVS1 prerequisite check
        "lof_mechanism":       True,
        "lof_mechanism_note":  "ENG causes HHT type 1 via haploinsufficiency; frameshift, nonsense, and splice variants are well-established pathogenic mechanisms.",
    },
    # ── Non-VCEP genes — add as needed for ACMG mode ──────────────────────────
    "LDLR": {
        "gene_symbol":    "LDLR",
        "transcripts":    ["NM_000527"],        # NM_000527.x (any version)
        "protein_length": 860,                  # aa
        "total_exons":    18,
        "cspec_id":       None,                 # no VCEP spec
        # LOF mechanism — used by PVS1 prerequisite check
        "lof_mechanism":       True,
        "lof_mechanism_note":  "LDLR causes Familial Hypercholesterolemia via haploinsufficiency; frameshift, nonsense, and canonical splice variants account for ~30% of pathogenic LDLR alleles and are well-established disease-causing mechanisms.",
    },
}


def get_gene_from_transcript(transcript_id: str) -> str | None:
    """
    Maps a transcript accession (NM_...) to a GENE_DB gene symbol.
    Strips version numbers (e.g. NM_001114753.3 → NM_001114753).
    Returns None if the transcript is not in GENE_DB.
    """
    bare = transcript_id.split(".")[0]
    for gene_symbol, info in GENE_DB.items():
        for t in info["transcripts"]:
            if bare == t:
                return gene_symbol
    return None


PLANRAG_DB = {

    # ══════════════════════════════════════════════════════════════════════════
    # PHASE 1 — gnomAD criteria (run first, no dependencies, others depend on these)
    # ══════════════════════════════════════════════════════════════════════════

    "PM2_SUPPORTING": {
        "criterion": "PM2_Supporting",
        "acmg_category": "Pathogenic",
        "strength": "supporting",
        "automation": "fully_automatable",
        "tool": "gnomad",
        "phase": 1,
        "depends_on": [],
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

    "BA1": {
        "criterion": "BA1",
        "acmg_category": "Benign",
        "strength": "stand_alone",
        "automation": "fully_automatable",
        "tool": "gnomad",
        "phase": 1,
        "depends_on": [],
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
        "phase": 1,
        "depends_on": [],
        "description": (
            "Allele frequency is greater than expected for the disorder. "
            "HHT VCEP defines two strength levels using Popmax FAF (bottlenecked populations included): "
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
            "  - YES → BS1_Strong APPLIES via homozygote route. Set applies=true, applied_strength=benign_strong. Stop.\n"
            "  - NO  → continue to Step 3.\n"
            "\n"
            "STEP 3: Check for BS1_Strong via the FAF route.\n"
            "  Is Popmax FAF > 0.002 AND < 0.01?\n"
            "  - YES → BS1_Strong APPLIES. Set applies=true, applied_strength=benign_strong. Stop.\n"
            "  - NO  → continue to Step 4.\n"
            "\n"
            "STEP 4: Check for BS1_Supporting.\n"
            "  Is Popmax FAF > 0.0008 AND <= 0.002?\n"
            "  - YES → BS1_Supporting APPLIES. Set applies=true, applied_strength=benign_supporting. Stop.\n"
            "  - NO  → BS1 does NOT apply. Set applies=false.\n"
            "\n"
            "IMPORTANT: Set applied_strength to exactly 'benign_strong' or 'benign_supporting' (not 'strong' or 'supporting').\n"
            "NOTE: If BS1 or BS1_Supporting applies, PP4_Moderate cannot be applied.\n"
            "Record exact Popmax FAF, homozygote count, and which strength level triggered."
        ),
        "hht_modification": "Two strength levels (Strong: >0.2-<1% OR BS1_Sup + 2 homozygotes; Supporting: >0.08-0.2%); Popmax FAF including bottlenecked populations; blocks PP4_Moderate",
        "strength_override": None,
    },

    # ══════════════════════════════════════════════════════════════════════════
    # PHASE 2 — depends on Phase 1 results
    # ══════════════════════════════════════════════════════════════════════════

    "PS4": {
        "criterion": "PS4",
        "acmg_category": "Pathogenic",
        "strength": "strong",
        "automation": "partially_automatable",
        "tool": "clinvar",
        "phase": 2,
        "depends_on": ["PM2_SUPPORTING"],
        "requires_applied": ["PM2_SUPPORTING"],
        "blocked_by": [],
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
            "PM2_Supporting has already been confirmed as met — do not re-evaluate it.\n"
            "Query ClinVar for the HHT VCEP expert panel submission for this variant.\n"
            "The submission comment contains the proband count reported by submitting labs.\n"
            "If the variant is not in ClinVar or has no proband count, fall back to PubMed.\n"
            "\n"
            "STEP 1: Extract proband count from the ClinVar HHT VCEP SCV comment,\n"
            "        or from PubMed case reports if ClinVar has no data.\n"
            "  Rules for counting:\n"
            "    - Each proband must have phenotype consistent with HHT.\n"
            "    - Exclude duplicate reports of the same patient across papers.\n"
            "    - Do NOT count probands who qualify for PP4_Moderate.\n"
            "\n"
            "STEP 2: Apply strength based on proband count:\n"
            "  - Count >= 4 → PS4_Strong applies. Set applies=true, strength=strong.\n"
            "  - Count = 2 or 3 → PS4_Moderate applies. Set applies=true, strength=moderate.\n"
            "  - Count = 1 → PS4_Supporting applies. Set applies=true, strength=supporting.\n"
            "  - Count = 0 → PS4 does NOT apply. Set applies=false.\n"
            "\n"
            "Record proband count, source (ClinVar or PubMed), and strength level in evidence."
        ),
        "hht_modification": "Proband-based counting (4+ Strong / 2-3 Moderate / 1 Supporting); requires PM2_Supporting; PP4_Moderate probands excluded from count",
        "strength_override": None,
    },

    "PP4_MODERATE": {
        "criterion": "PP4_Moderate",
        "acmg_category": "Pathogenic",
        "strength": "moderate",
        "automation": "not_automatable",
        "tool": None,
        "phase": 2,
        "depends_on": [],
        "blocked_by": ["BA1", "BS1", "BS1_SUPPORTING"],
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

    # ── PM1: gene-specific critical residues ─────────────────────────────────
    # gene_data branches are merged into the returned entry by query(criterion, gene=...).
    # Shared fields (criterion, phase, tool, etc.) are at the top level.
    # Gene-specific fields (critical_regions, description, threshold, instructions) live in gene_data.
    # Default (no gene specified) → ACVRL1 branch for backward compatibility.

    "PM1": {
        "criterion": "PM1",
        "acmg_category": "Pathogenic",
        "strength": "moderate",
        "automation": "fully_automatable",
        "tool": "vep",
        "phase": 2,
        "depends_on": [],
        "blocks": ["PM5_Strong"],
        "variant_types": ["missense"],
        "strength_override": "moderate",

        "gene_data": {
            "ACVRL1": {
                "critical_regions": {
                    "ranges": [
                        {"start": 209, "end": 216, "name": "glycine-rich loop (G209-V216)"},
                        {"start": 229, "end": 229, "name": "phosphate anchor (K229)"},
                        {"start": 242, "end": 242, "name": "C-helix E / phosphate anchor pairing (E242)"},
                        {"start": 329, "end": 335, "name": "catalytic loop (R329-N335)"},
                        {"start": 348, "end": 351, "name": "metal-binding loop (D348-L351)"},
                    ],
                    "discrete": [
                        {"positions": [40, 54, 56, 57, 58, 59, 66, 71, 72, 73, 75, 76, 78, 79, 80, 82, 83, 84, 85, 87],
                         "name": "BMP10 interaction cluster"},
                    ],
                },
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
            },

            "ENG": {
                "critical_regions": {
                    "ranges": [],
                    "discrete": [
                        {"positions": [278, 282],
                         "name": "BMP9 binding sites (PMIDs 28564608, 25312062)"},
                        {"positions": [207, 363, 382, 412, 549],
                         "name": "cysteine residues classified LP/P by HHT VCEP"},
                        {"positions": [350, 394],
                         "name": "cysteine residues critical to ENG function (disulfide bonds)"},
                    ],
                },
                "description": (
                    "Variant located in a critical residue of ENG (endoglin). "
                    "HHT VCEP defines specific critical residues for ENG based on structural and functional data: "
                    "BMP9 binding sites (Tyr278, Thr282), "
                    "cysteine residues classified LP/P by HHT VCEP (Cys207, Cys363, Cys382, Cys412, Cys549), "
                    "and cysteine residues critical to ENG function via disulfide bonds (Cys350, Cys394). "
                    "PM1 applies only at Moderate strength. "
                    "If variant falls within a PM1 region, do not use PM1 with PM5_Strong; PM1 + PM5 (Moderate) is allowed."
                ),
                "threshold": "Variant residue is in: BMP9 binding sites {278, 282} OR LP/P-classified cysteines {207, 363, 382, 412, 549} OR disulfide-bond cysteines {350, 394}",
                "instructions": (
                    "Determine the protein position of the variant on ENG (NM_001114753.3). "
                    "PM1_Moderate applies if the residue is in ANY of these critical positions: "
                    "(1) BMP9 binding sites: positions 278, 282; "
                    "(2) cysteine residues classified LP/P by HHT VCEP: positions 207, 363, 382, 412, 549; "
                    "(3) cysteine residues critical to ENG function (disulfide bonds): positions 350, 394. "
                    "This is a hardcoded residue list per CSpec GN136 — no UniProt lookup needed, no LLM judgment needed. "
                    "RULE: if PM1 applies, do NOT combine with PM5_Strong. PM1 + PM5 (Moderate) IS allowed."
                ),
                "hht_modification": "Hardcoded critical residue list per CSpec GN136 v1.1.0; Moderate strength only; cannot combine with PM5_Strong",
            },
        },
    },

    # ══════════════════════════════════════════════════════════════════════════
    # PHASE 3 — depends on Phase 2 results
    # ══════════════════════════════════════════════════════════════════════════

    # ── PVS1: gene-specific decision tree boundaries ──────────────────────────
    # Shared fields are at the top level.
    # Gene-specific fields (nmd_boundary, critical_region_boundary, description,
    # threshold, instructions) live in gene_data.
    # Default (no gene specified) → ACVRL1 branch for backward compatibility.

    "PVS1": {
        "criterion": "PVS1",
        "acmg_category": "Pathogenic",
        "strength": "very_strong",
        "automation": "fully_automatable",
        "tool": "vep",
        "phase": 3,
        "depends_on": [],
        "blocks": ["PS3_for_splice_variants"],
        "variant_types": ["frameshift", "nonsense", "splice_site", "start_lost"],
        "strength_override": None,

        "gene_data": {
            "ACVRL1": {
                "nmd_boundary":             442,   # codons <= this → NMD predicted
                "critical_region_boundary": 490,   # codons <= this → truncated region critical
                "description": (
                    "Null variant in ACVRL1 evaluated by the HHT VCEP PVS1 decision tree. "
                    "Final strength (Very Strong / Strong / Moderate / N/A) depends on variant type, NMD prediction, "
                    "and codon position. Key codon thresholds: codon 442 (NMD boundary), codon 490 (critical region boundary)."
                ),
                "threshold": "ACVRL1: Codon 442 (NMD boundary); Codon 490 (critical region boundary); protein length 503 aa",
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
            },

            "ENG": {
                # ⚠ VERIFY: codon boundaries below are estimated from ENG gene structure.
                # ENG protein = 658 aa, 15 exons. NMD boundary and critical region boundary
                # must be confirmed against GN136 PDF (ClinGen HHT VCEP CSpec documentation).
                # Estimated: NMD boundary ~codon 594 (last exon-exon junction, exon 14/15).
                #            Critical region boundary ~codon 580 (start of exon 14 intracellular domain).
                "nmd_boundary":             594,   # ⚠ VERIFY from GN136 PDF
                "critical_region_boundary": 580,   # ⚠ VERIFY from GN136 PDF
                "description": (
                    "Null variant in ENG evaluated by the HHT VCEP PVS1 decision tree. "
                    "Final strength (Very Strong / Strong / Moderate / N/A) depends on variant type, NMD prediction, "
                    "and codon position. Key codon thresholds: codon 594 (NMD boundary, ⚠ verify), "
                    "codon 580 (critical region boundary, ⚠ verify). "
                    "ENG exon 13 frameshifts are predicted NMD per VCEP evidence."
                ),
                "threshold": "ENG: Codon 594 (NMD boundary, ⚠ verify); Codon 580 (critical region boundary, ⚠ verify); protein length 658 aa",
                "instructions": (
                    "Use VEP to determine variant consequence and protein codon position. "
                    "Then apply the ENG PVS1 Decision Tree (CSpec GN136 v1.1.0):\n"
                    "NOTE: Codon boundary values below are estimated — verify against GN136 PDF before production use.\n"
                    "\n"
                    "NONSENSE OR FRAMESHIFT:\n"
                    "  - Predicted to undergo NMD (codon <=594) → PVS1 (Very Strong)\n"
                    "    Example: frameshift in exon 13/15 → NMD confirmed per HHT VCEP.\n"
                    "  - Not predicted to undergo NMD (codon >594):\n"
                    "      * Truncated/altered region critical to protein function (codon <=580) → PVS1_Strong\n"
                    "      * Role of region unknown AND variant removes <10% of protein → PVS1_Moderate\n"
                    "\n"
                    "GT-AG +/-1,2 SPLICE SITES:\n"
                    "  - Exon skipping or cryptic splice disrupts reading frame, predicted NMD (codon <=594) → PVS1\n"
                    "  - Exon skipping or cryptic splice disrupts reading frame, NOT predicted NMD (codon >594):\n"
                    "      * Truncated/altered region critical (codon <=580, see also PM1 regions) → PVS1_Strong\n"
                    "      * Role of region unknown AND variant removes <10% of protein → PVS1_Moderate\n"
                    "  - Exon skipping or cryptic splice preserves reading frame:\n"
                    "      * Truncated/altered region critical (codon <=580) → PVS1_Strong\n"
                    "      * Role of region unknown AND variant removes <10% of protein → PVS1_Moderate\n"
                    "\n"
                    "DELETION (single exon to full gene):\n"
                    "  - Full gene deletion → PVS1\n"
                    "  - Single/multi-exon deletion disrupts reading frame, predicted NMD, exon in biologically-relevant transcript → PVS1\n"
                    "  - Single/multi-exon deletion disrupts reading frame, NOT predicted NMD:\n"
                    "      * Truncated/altered region critical (codon <=580) → PVS1_Strong\n"
                    "      * Role of region unknown AND variant removes <10% of protein → PVS1_Moderate\n"
                    "  - Single/multi-exon deletion preserves reading frame:\n"
                    "      * Truncated/altered region critical (codon <=580) → PVS1_Strong\n"
                    "\n"
                    "DUPLICATION (>=1 exon, fully within gene):\n"
                    "  - Proven in tandem AND reading frame disrupted AND NMD predicted → PVS1\n"
                    "  - Proven in tandem AND no/unknown impact on reading frame and NMD → N/A\n"
                    "  - Presumed in tandem AND reading frame presumed disrupted AND NMD predicted → PVS1_Strong\n"
                    "  - Proven NOT in tandem → N/A\n"
                    "\n"
                    "INITIATION CODON:\n"
                    "  - No known alternative start codon in other ENG transcripts → PVS1_Moderate\n"
                    "\n"
                    "Record the variant type, codon position, NMD prediction, and final strength."
                ),
                "hht_modification": "Decision tree with codon 594 NMD boundary (⚠ verify) and codon 580 critical region boundary (⚠ verify); protein length 658 aa; 15 exons",
            },
        },
    },

    "PM5": {
        "criterion": "PM5",
        "acmg_category": "Pathogenic",
        "strength": "moderate",
        "automation": "partially_automatable",
        "tool": "erepo",
        "phase": 3,
        "depends_on": ["PM1"],
        "variant_types": ["missense"],
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

    "PS3": {
        "criterion": "PS3",
        "acmg_category": "Pathogenic",
        "strength": "strong",
        "automation": "not_automatable",
        "tool": None,
        "phase": 3,
        "depends_on": ["PVS1"],
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

    # ══════════════════════════════════════════════════════════════════════════
    # PHASE 4 — no dependencies, can run in any order
    # ══════════════════════════════════════════════════════════════════════════

    "PS1": {
        "criterion": "PS1",
        "acmg_category": "Pathogenic",
        "strength": "strong",
        "automation": "partially_automatable",
        "tool": "clinvar",
        "phase": 4,
        "depends_on": [],
        "variant_types": ["missense"],
        "description": (
            "Same amino acid change as a previously established pathogenic variant regardless of nucleotide change. "
            "HHT VCEP applies no modification — use as in original ACMG (Strong only). "
            "Caveat: beware of changes that impact splicing rather than at the amino acid/protein level."
        ),
        "threshold": "Same amino acid change as established pathogenic variant",
        "instructions": (
            "Search for variants producing the same amino acid change as the query variant\n"
            "(regardless of nucleotide change).\n"
            "\n"
            "STEP 1: Does an HHT VCEP-classified entry exist with the same amino acid change?\n"
            "  - NO  → PS1 does NOT apply. Set applies=false. Stop.\n"
            "  - YES → continue to Step 2.\n"
            "\n"
            "STEP 2: Is the classification Pathogenic or Likely Pathogenic?\n"
            "  - NO  → PS1 does NOT apply. Set applies=false. Stop.\n"
            "  - YES → continue to Step 3.\n"
            "\n"
            "STEP 3: Could the query variant affect splicing rather than the amino acid change?\n"
            "  - YES → PS1 is NOT appropriate. Set applies=false.\n"
            "  - NO  → PS1 APPLIES. Set applies=true. Strength is Strong only.\n"
            "\n"
            "Record the matched variant, classification, and amino acid change in evidence."
        ),
        "hht_modification": "No modification — use as in original ACMG; Strong strength only",
        "strength_override": "strong",
    },

    "PP3": {
        "criterion": "PP3",
        "acmg_category": "Pathogenic",
        "strength": "supporting",
        "automation": "fully_automatable",
        "tool": "revel_spliceai",
        "phase": 4,
        "depends_on": [],
        "blocked_by": ["PVS1"],   # computational evidence is redundant when PVS1 (null variant) applies
        "variant_types": ["missense", "synonymous", "intronic", "splice_region", "splice_site"],
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
            "  STEP 2: Is ANY SpliceAI delta score >= 0.2?\n"
            "    - YES → PP3 APPLIES. Set applies=true. Stop. Record which score triggered.\n"
            "    - NO  → PP3 does NOT apply. Set applies=false.\n"
            "\n"
            "BRANCH B — Synonymous or intronic variant:\n"
            "  STEP 1: Is ANY SpliceAI delta score >= 0.2?\n"
            "    - YES → PP3 APPLIES. Set applies=true. Record which score triggered.\n"
            "    - NO  → PP3 does NOT apply. Set applies=false.\n"
            "\n"
            "IMPORTANT: For missense, REVEL and SpliceAI are independent triggers (OR logic).\n"
            "Record exact scores and which threshold triggered in the evidence field."
        ),
        "hht_modification": "Supporting strength only; thresholds: REVEL >=0.644 (missense); SpliceAI >=0.2 (any variant type)",
        "strength_override": "supporting",
    },

    "PM4": {
        "criterion": "PM4",
        "acmg_category": "Pathogenic",
        "strength": "moderate",
        "automation": "fully_automatable",
        "tool": "vep",
        "phase": 4,
        "depends_on": [],
        "variant_types": ["inframe_insertion", "inframe_deletion", "stop_lost"],
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
            "  - YES → PM4 does NOT apply. Set applies=false.\n"
            "  - NO  → PM4_Moderate APPLIES. Set applies=true.\n"
            "\n"
            "Record VEP consequence and repeat region status in evidence."
        ),
        "hht_modification": "No modification — use as in original ACMG",
        "strength_override": "moderate",
    },

    "BP4": {
        "criterion": "BP4",
        "acmg_category": "Benign",
        "strength": "supporting",
        "automation": "fully_automatable",
        "tool": "revel_spliceai",
        "phase": 4,
        "depends_on": [],
        "blocked_by": ["PVS1"],   # computational evidence is redundant when PVS1 (null variant) applies
        "variant_types": ["missense", "synonymous", "intronic", "splice_region", "splice_site"],
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
            "  STEP 2: Are ALL four SpliceAI delta scores <= 0.1?\n"
            "    - NO  (any score > 0.1) → BP4 does NOT apply. Set applies=false. Stop.\n"
            "    - YES (all scores <= 0.1) → BP4 APPLIES. Set applies=true.\n"
            "\n"
            "BRANCH B — Synonymous or intronic variant (SpliceAI only):\n"
            "  STEP 1: Are ALL four SpliceAI delta scores <= 0.1?\n"
            "    - NO  (any score > 0.1) → BP4 does NOT apply. Set applies=false.\n"
            "    - YES (all scores <= 0.1) → BP4 APPLIES. Set applies=true.\n"
            "\n"
            "IMPORTANT: For missense, failing EITHER condition means BP4 does NOT apply (AND logic, not OR).\n"
            "Record exact REVEL and SpliceAI scores in evidence."
        ),
        "hht_modification": "Missense requires BOTH REVEL <=0.15 AND SpliceAI <=0.1 (not OR); synonymous/intronic uses SpliceAI <=0.1 only",
        "strength_override": "supporting",
    },

    "BP7": {
        "criterion": "BP7",
        "acmg_category": "Benign",
        "strength": "supporting",
        "automation": "fully_automatable",
        "tool": "spliceai",
        "phase": 4,
        "depends_on": [],
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

    # ── Phase 4: Not automatable (deferred) ──────────────────────────────────

    "PP1": {
        "criterion": "PP1",
        "acmg_category": "Pathogenic",
        "strength": "supporting",
        "automation": "not_automatable",
        "tool": None,
        "phase": 4,
        "depends_on": [],
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

    "BS3": {
        "criterion": "BS3",
        "acmg_category": "Benign",
        "strength": "supporting",
        "automation": "not_automatable",
        "tool": None,
        "phase": 4,
        "depends_on": [],
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
        "phase": 4,
        "depends_on": [],
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
        "automation": "not_automatable",
        "tool": None,
        "phase": 4,
        "depends_on": [],
        "description": (
            "Observed in trans with a pathogenic or likely pathogenic variant (per HHT VCEP rules). "
            "HHT VCEP applies BP2 at Supporting strength only. "
            "REQUIREMENT: variants must be confirmed in trans (phase confirmed)."
        ),
        "threshold": "Confirmed in trans with a P/LP variant classified per HHT VCEP rules",
        "instructions": (
            "BP2 cannot be evaluated automatically. "
            "Requires patient-level phasing data (parental testing or read-based phasing). "
            "Return applies=null, status=deferred, with explanation."
        ),
        "hht_modification": "Supporting strength only; phase must be confirmed; reference variant must be HHT VCEP-classified P/LP",
        "strength_override": "supporting",
        "deferred": True,
    },

    # ── BP5: gene-specific — references the other HHT gene ───────────────────
    # For an ACVRL1 variant: BP5 applies when a P/LP ENG variant is also found.
    # For an ENG variant: BP5 applies when a P/LP ACVRL1 variant is also found.

    "BP5": {
        "criterion": "BP5",
        "acmg_category": "Benign",
        "strength": "supporting",
        "automation": "not_automatable",
        "tool": None,
        "phase": 4,
        "depends_on": [],
        "strength_override": "supporting",
        "deferred": True,

        "gene_data": {
            "ACVRL1": {
                "description": (
                    "Variant found in a case with an alternate molecular basis for disease. "
                    "HHT VCEP applies BP5 at Supporting strength when: a likely pathogenic or pathogenic variant "
                    "(per HHT VCEP rules) is identified in ENG in the same patient."
                ),
                "threshold": "Patient also carries a P/LP variant in ENG (per HHT VCEP rules)",
                "instructions": (
                    "BP5 cannot be evaluated automatically. "
                    "Requires patient-level data showing co-occurrence of a P/LP ENG variant in the same patient. "
                    "Return applies=null, status=deferred, with explanation."
                ),
                "hht_modification": "Supporting strength only; specifically applies when a P/LP ENG variant (HHT VCEP rules) is found in the same patient",
            },
            "ENG": {
                "description": (
                    "Variant found in a case with an alternate molecular basis for disease. "
                    "HHT VCEP applies BP5 at Supporting strength when: a likely pathogenic or pathogenic variant "
                    "(per HHT VCEP rules) is identified in ACVRL1 in the same patient."
                ),
                "threshold": "Patient also carries a P/LP variant in ACVRL1 (per HHT VCEP rules)",
                "instructions": (
                    "BP5 cannot be evaluated automatically. "
                    "Requires patient-level data showing co-occurrence of a P/LP ACVRL1 variant in the same patient. "
                    "Return applies=null, status=deferred, with explanation."
                ),
                "hht_modification": "Supporting strength only; specifically applies when a P/LP ACVRL1 variant (HHT VCEP rules) is found in the same patient",
            },
        },
    },

    # ══════════════════════════════════════════════════════════════════════════
    # SCORING — HHT VCEP combining criteria rules (CSpec GN135/GN136 v1.1.0)
    # Source: https://cspec.genome.network/cspec/ui/svi/doc/GN135#rules-combinations-panel-1576018580
    #
    # Each applied criterion maps to a strength bucket.
    # Fixed-strength criteria always land in the same bucket (enforced in task_agent.py).
    # Variable-strength criteria (PVS1, PS3, PS4, PM5, PP1) land in the bucket
    # corresponding to their applied_strength field.
    #
    # Bucket → contribution to rule counts:
    #   "very_strong"       → vs  (pathogenic)
    #   "strong"            → s   (pathogenic)
    #   "moderate"          → m   (pathogenic)
    #   "supporting"        → sup (pathogenic)
    #   "benign_stand_alone"→ ba  (benign — auto-Benign, evaluated first)
    #   "benign_strong"     → bs  (benign)
    #   "benign_supporting" → bsup(benign)
    #
    # Incompatibility rule: PM1 + PM5_Strong → downgrade PM5 to moderate before bucketing.
    # ══════════════════════════════════════════════════════════════════════════

    "SCORING": {
        "criterion": "SCORING",

        # Maps criterion key → its fixed bucket (enforced in task_agent.py for these;
        # listed here as the single source of truth for the scoring module too).
        # Variable-strength criteria are NOT listed here — they use applied_strength.
        "fixed_strengths": {
            "PM2_SUPPORTING": "supporting",
            "PP3":            "supporting",
            "PP4_MODERATE":   "moderate",
            "PM1":            "moderate",
            "PM4":            "moderate",
            "PS1":            "strong",
            "PS2":            "strong",   # excluded in HHT VCEP but kept for completeness
            "BA1":            "benign_stand_alone",
            # BS1 is NOT here — it has two strength levels (benign_strong / benign_supporting)
            # and is treated as a variable-strength criterion (see variable_strength_map below).
            "BS3_SUPPORTING": "benign_supporting",
            "BS4":            "benign_strong",
            "BP2":            "benign_supporting",
            "BP4":            "benign_supporting",
            "BP5":            "benign_supporting",
            "BP7":            "benign_supporting",
        },

        # Variable-strength criteria: applied_strength string → bucket.
        # Used for PVS1, PS3, PS4, PM5, PP1 (pathogenic variable-strength) and
        # BS1 (benign variable-strength: benign_strong or benign_supporting).
        "variable_strength_map": {
            "very_strong":       "very_strong",
            "strong":            "strong",
            "moderate":          "moderate",
            "supporting":        "supporting",
            # Benign variable-strength buckets (used by BS1)
            "benign_strong":     "benign_strong",
            "benign_supporting": "benign_supporting",
        },

        # Incompatible combinations — handled before bucketing.
        # Format: list of {"criteria": [...], "action": "...", "target": "...", "new_strength": "..."}
        "incompatible_combinations": [
            {
                "criteria":   ["PM1", "PM5"],
                "condition":  "PM5 applied_strength == strong",
                "action":     "downgrade",
                "target":     "PM5",
                "new_strength": "moderate",
                "note": "PM1 and PM5_Strong cannot be combined — PM5 is downgraded to Moderate",
            },
        ],

        # ── PATHOGENIC combining rules ─────────────────────────────────────────
        # Each rule specifies minimum counts that must be satisfied simultaneously.
        # Keys: vs (very strong), s (strong), m (moderate), sup (supporting).
        # Missing keys default to 0 (i.e. no requirement on that bucket).
        # Rules are checked in order — first match wins.
        "pathogenic_rules": [
            {"vs": 1, "s": 1,                     "label": "PVS1 + ≥1 Strong"},
            {"vs": 1, "m": 2,                     "label": "PVS1 + ≥2 Moderate"},
            {"vs": 1, "m": 1, "sup": 1,           "label": "PVS1 + 1 Moderate + 1 Supporting"},
            {"vs": 1, "sup": 2,                   "label": "PVS1 + ≥2 Supporting"},
            {"s": 2,                               "label": "≥2 Strong"},
            {"s": 1, "m": 3,                       "label": "1 Strong + ≥3 Moderate"},
            {"s": 1, "m": 2, "sup": 2,            "label": "1 Strong + 2 Moderate + ≥2 Supporting"},
            {"s": 1, "m": 1, "sup": 4,            "label": "1 Strong + 1 Moderate + ≥4 Supporting"},
        ],

        # ── LIKELY PATHOGENIC combining rules ─────────────────────────────────
        "likely_pathogenic_rules": [
            {"vs": 1, "m": 1,                     "label": "PVS1 + 1 Moderate"},
            {"vs": 1, "sup": 1,                   "label": "PVS1 + 1 Supporting"},
            {"s": 1, "m": 2,                       "label": "1 Strong + 2 Moderate"},
            {"s": 1, "m": 1,                       "label": "1 Strong + 1 Moderate"},
            {"s": 1, "sup": 2,                    "label": "1 Strong + ≥2 Supporting"},
            {"m": 3,                               "label": "≥3 Moderate"},
            {"m": 2, "sup": 2,                    "label": "2 Moderate + ≥2 Supporting"},
            {"m": 1, "sup": 4,                    "label": "1 Moderate + ≥4 Supporting"},
        ],

        # ── BENIGN combining rules (checked before pathogenic) ─────────────────
        # Keys: ba (stand-alone), bs (strong), bsup (supporting).
        "benign_rules": [
            {"ba": 1,          "label": "BA1 stand-alone"},
            {"bs": 2,          "label": "≥2 Strong benign"},
        ],

        # ── LIKELY BENIGN combining rules ──────────────────────────────────────
        "likely_benign_rules": [
            {"bs": 1, "bsup": 1, "label": "1 Strong + 1 Supporting benign"},
            {"bs": 1,            "label": "1 Strong benign"},
            {"bsup": 2,          "label": "≥2 Supporting benign"},
        ],
    },
}


# ──────────────────────────────────────────────────────────────────────────────
# EXCLUDED CRITERIA — Not Applicable per HHT VCEP CSpec GN135/GN136 v1.1.0
# ──────────────────────────────────────────────────────────────────────────────

EXCLUDED_CRITERIA = {
    "PS2": "Not Applicable per HHT VCEP — de novo variants are rare in HHT; should be confirmed not presumed. Low-level mosaicism in parents has been observed.",
    "PM3": "Not Applicable per HHT VCEP — HHT is autosomal dominant; AR trans mechanism not relevant",
    "PM6": "Not Applicable per HHT VCEP — de novo variants are rare in HHT; should be confirmed not presumed",
    "PP5": "Not Applicable per ClinGen SVI VCEP Review Committee (PMID: 29543229)",
    "BS2": "Not Applicable per HHT VCEP — full penetrance at an early age is not observed in HHT",
    "BP1": "Not Applicable per HHT VCEP — missense variants commonly seen in HHT genes",
    "BP3": "Not Applicable per HHT VCEP",
    "BP6": "Not Applicable per ClinGen SVI VCEP Review Committee (PMID: 29543229)",
}


# ──────────────────────────────────────────────────────────────────────────────
# VCEP DISEASE REGISTRY
# Add new VCEPs here as they are implemented. Keys are uppercase disease names.
# The pipeline checks this registry to decide whether to use PLANRAG_DB (VCEP)
# or ACMG_PLANRAG_DB (generic ACMG/AMP 2015).
# ──────────────────────────────────────────────────────────────────────────────

VCEP_DISEASES = {
    "HHT": "Hereditary Hemorrhagic Telangiectasia",
}


def is_vcep_disease(disease: str) -> bool:
    """Returns True if the disease has a ClinGen VCEP specification in VCEP_DISEASES."""
    if not disease:
        return False
    return disease.upper() in VCEP_DISEASES


# ──────────────────────────────────────────────────────────────────────────────
# ACMG/AMP 2015 PLANRAG DATABASE — generic criteria (non-VCEP diseases)
# Source: Richards et al. Genet Med 2015;17(5):405–424 (PMC4544753)
#
# Used when disease is provided but is NOT in VCEP_DISEASES.
# Follows the same entry structure as PLANRAG_DB.
#
# EXECUTION ORDER:
#   Phase 1: PM2, BA1, BS1, BS2  (gnomAD — no dependencies)
#   Phase 2: PS4, PM1             (PS4 independent; PM1 needed before PM5)
#   Phase 3: PVS1, PM5            (PM5 depends on PM1 implicitly)
#   Phase 4: PS1, PP3, PP5, BP3, BP4, BP6, BP7, PM4  (no dependencies)
#
# Deferred (require expert input or non-automatable data):
#   PS2, PS3, PM3, PM6, PP1, PP4, BS3, BS4, BP1, BP2, BP5
#
# Coverage notes:
#   - BP1 deferred until gnomAD gene-level constraint query is implemented
#   - BS2 partially automatable for dominant/X-linked via gnomAD ac_hom
#   - PM1 partially automatable via VEP codon position + LLM protein domain knowledge
#   - PP5 and BP6 are now applicable (excluded in HHT VCEP)
#   - BP3 is now applicable (excluded in HHT VCEP)
#   - PM2 is Moderate strength (not Supporting as in some VCEP specifications)
#
# Key normalization: VCEP-style names (e.g. PM2_SUPPORTING, PP4_MODERATE) are
# automatically mapped to their standard ACMG equivalents when querying this DB.
# ──────────────────────────────────────────────────────────────────────────────

# Maps VCEP-style criterion names → standard ACMG names, for backward compatibility
# when the pipeline passes VCEP-style strings into a generic ACMG query.
_ACMG_KEY_ALIASES = {
    "PM2_SUPPORTING": "PM2",
    "PP4_MODERATE":   "PP4",
    "BS1_SUPPORTING": "BS1",
    "BS3_SUPPORTING": "BS3",
}

ACMG_PLANRAG_DB = {

    # ══════════════════════════════════════════════════════════════════════════
    # PHASE 1 — population frequency (no dependencies)
    # ══════════════════════════════════════════════════════════════════════════

    "PM2": {
        "criterion": "PM2",
        "acmg_category": "Pathogenic",
        "strength": "moderate",
        "automation": "fully_automatable",
        "tool": "gnomad",
        "phase": 1,
        "depends_on": [],
        "description": (
            "Absent from controls (or at extremely low frequency if recessive) in population databases. "
            "ACMG standard: absent from gnomAD entirely OR allele frequency <0.0001 (0.01%) in any subpopulation. "
            "Applied at Moderate strength per ACMG/AMP 2015."
        ),
        "threshold": "Absent from gnomAD OR AF <0.0001 (0.01%) in any gnomAD subpopulation",
        "instructions": (
            "Query gnomAD for the variant. Retrieve total allele count (AC) and per-subpopulation allele frequencies.\n"
            "IMPORTANT: The evidence contains '_computed.verdicts' with pre-verified threshold comparisons. "
            "Read '_computed.pm2_applies' and set applies accordingly — do NOT recompute frequency comparisons yourself.\n"
            "\n"
            "STEP 1: Is the variant absent from gnomAD entirely?\n"
            "  - YES → PM2 APPLIES. Set applies=true. Stop.\n"
            "  - NO  → continue to Step 2.\n"
            "\n"
            "STEP 2: Is allele frequency in ALL gnomAD subpopulations less than 0.0001 (0.01%)?\n"
            "  - YES (all AFs < 0.0001) → PM2 APPLIES. Set applies=true. Stop.\n"
            "  - NO  (any AF >= 0.0001) → continue to Step 3.\n"
            "\n"
            "STEP 3 (recessive disorders only): Is total allele count below the expected carrier frequency?\n"
            "  - Below expected carrier frequency for this recessive disorder → PM2 APPLIES. Set applies=true.\n"
            "  - At or above expected carrier frequency → PM2 does NOT apply. Set applies=false.\n"
            "\n"
            "For dominant disorders: use Steps 1–2 only.\n"
            "Record total AC, max subpopulation AF, and which step triggered the decision."
        ),
        "strength_override": "moderate",
    },

    "BA1": {
        "criterion": "BA1",
        "acmg_category": "Benign",
        "strength": "stand_alone",
        "automation": "fully_automatable",
        "tool": "gnomad",
        "phase": 1,
        "depends_on": [],
        "description": (
            "Allele frequency is above 5% in population databases — stand-alone benign. "
            "ACMG standard threshold: >5% (0.05) in gnomAD, ExAC, or 1000 Genomes."
        ),
        "threshold": "Popmax FAF >= 0.05 (5%) in gnomAD",
        "instructions": (
            "Query gnomAD for Popmax Filtering Allele Frequency (FAF95, popmax field).\n"
            "IMPORTANT: Read '_computed.ba1_applies' from the evidence — this is pre-computed. Set applies to that value.\n"
            "\n"
            "STEP 1: Is Popmax FAF >= 0.05 (5%)?\n"
            "  - YES → BA1 APPLIES. Set applies=true.\n"
            "    Stand-alone benign — variant is Benign regardless of other evidence.\n"
            "  - NO  → BA1 does NOT apply. Set applies=false.\n"
            "  - Variant absent from gnomAD → BA1 does NOT apply. Set applies=false.\n"
            "\n"
            "Record exact Popmax FAF in evidence."
        ),
        "strength_override": "benign_stand_alone",
    },

    "BS1": {
        "criterion": "BS1",
        "acmg_category": "Benign",
        "strength": "strong",
        "automation": "fully_automatable",
        "tool": "gnomad",
        "phase": 1,
        "depends_on": [],
        "description": (
            "Allele frequency is greater than expected for the disorder. "
            "Generic ACMG threshold: Popmax FAF > 1% (0.01) and < 5% (0.05). "
            "Disease-specific thresholds should be applied when known; "
            "1% is a conservative generic threshold for low-prevalence Mendelian disorders."
        ),
        "threshold": "Popmax FAF > 0.01 (1%) and < 0.05 (5%) in gnomAD",
        "instructions": (
            "Query gnomAD for Popmax FAF (faf95 popmax field).\n"
            "IMPORTANT: Read '_computed.bs1_applies' from the evidence — this is pre-computed. Set applies to that value.\n"
            "\n"
            "STEP 1: Does BA1 already apply (Popmax FAF >= 0.05)?\n"
            "  - YES → do NOT apply BS1; BA1 supersedes. Set applies=false. Stop.\n"
            "  - NO  → continue to Step 2.\n"
            "\n"
            "STEP 2: Is Popmax FAF > 0.01 (1%)?\n"
            "  - YES → BS1 APPLIES. Set applies=true, applied_strength=benign_strong.\n"
            "  - NO  → BS1 does NOT apply. Set applies=false.\n"
            "\n"
            "Note: if disease-specific expected carrier/disease frequency is known and lower than 1%, "
            "apply that threshold instead.\n"
            "Record exact Popmax FAF in evidence."
        ),
        "strength_override": "benign_strong",
    },

    "BS2": {
        "criterion": "BS2",
        "acmg_category": "Benign",
        "strength": "strong",
        "automation": "partially_automatable",
        "tool": "gnomad",
        "phase": 1,
        "depends_on": [],
        "description": (
            "Observed in a healthy adult individual for a recessive (homozygous), dominant (heterozygous), "
            "or X-linked (hemizygous) disorder, with full penetrance expected at an early age. "
            "For dominant/X-linked: ac_hom > 0 in gnomAD strongly implies benign. "
            "For recessive: requires homozygous healthy adults — use ac_hom as proxy with caution."
        ),
        "threshold": "ac_hom > 0 in gnomAD general population (dominant/X-linked); or homozygotes in healthy adults (recessive, with caveats)",
        "instructions": (
            "Query gnomAD for total homozygote count (ac_hom summed across exome + genome).\n"
            "IMPORTANT: Read '_computed.bs2_check_ac_hom' from the evidence (True = homozygotes present).\n"
            "\n"
            "FOR DOMINANT OR X-LINKED DISORDERS:\n"
            "  STEP 1: Is ac_hom (total homozygotes in gnomAD) > 0?\n"
            "    - YES → BS2 APPLIES. Set applies=true, applied_strength=benign_strong.\n"
            "      Rationale: healthy homozygotes in gnomAD are inconsistent with fully penetrant dominant disease.\n"
            "    - NO  → BS2 does NOT apply. Set applies=false.\n"
            "\n"
            "FOR RECESSIVE DISORDERS:\n"
            "  If the disorder is severe and early-onset AND ac_hom > 0 in gnomAD:\n"
            "    → BS2 likely APPLIES. Set applies=true, applied_strength=benign_strong.\n"
            "  Otherwise: flag as inconclusive and set applies=false.\n"
            "  Note: gnomAD does not confirm individuals are 'healthy adults'; assume general population.\n"
            "\n"
            "Record ac_hom count, inheritance assumption, and reasoning in evidence."
        ),
        "strength_override": "benign_strong",
    },

    # ══════════════════════════════════════════════════════════════════════════
    # PHASE 2
    # ══════════════════════════════════════════════════════════════════════════

    "PS4": {
        "criterion": "PS4",
        "acmg_category": "Pathogenic",
        "strength": "strong",
        "automation": "partially_automatable",
        "tool": "clinvar",
        "phase": 2,
        "depends_on": [],
        "description": (
            "The prevalence of the variant in affected individuals is significantly increased "
            "compared to controls. ACMG standard: OR or RR > 5.0 with CI not including 1.0. "
            "For rare variants: prior observation in multiple unrelated patients with the same phenotype, "
            "absent from controls, may be used as Moderate evidence."
        ),
        "threshold": "OR/RR > 5.0 (CI not including 1.0); or multiple unrelated patients with same phenotype absent from controls",
        "instructions": (
            "Search ClinVar and ClinGen ERepo for this variant's evidence. Fall back to PubMed.\n"
            "\n"
            "STEP 1: Gather case-level evidence (proband counts, case reports, statistical data).\n"
            "\n"
            "STEP 2: Apply strength based on evidence type:\n"
            "  - OR/RR > 5.0 with CI not including 1.0 (case-control study) → PS4_Strong. applied_strength=strong.\n"
            "  - >=4 unrelated patients with same phenotype, absent from controls → PS4_Strong. applied_strength=strong.\n"
            "  - 2–3 unrelated patients with same phenotype → PS4_Moderate. applied_strength=moderate.\n"
            "  - 1 patient with same phenotype → PS4_Supporting. applied_strength=supporting.\n"
            "  - No case evidence → PS4 does NOT apply. Set applies=false.\n"
            "\n"
            "Record patient count or statistical values and source in evidence."
        ),
        "strength_override": None,
    },

    "PM1": {
        "criterion": "PM1",
        "acmg_category": "Pathogenic",
        "strength": "moderate",
        "automation": "partially_automatable",
        "tool": "vep",
        "phase": 2,
        "depends_on": [],
        "blocks": ["PM5_Strong"],
        "variant_types": ["missense"],
        "description": (
            "Located in a mutational hot spot and/or critical and well-established functional domain "
            "(e.g. active site of an enzyme) without benign variation. ACMG Moderate strength. "
            "VEP provides the codon position; domain membership is assessed using LLM knowledge "
            "of the gene's protein structure and known functional regions."
        ),
        "threshold": "Variant in a mutational hotspot or critical functional domain with no known benign variation at that position",
        "instructions": (
            "Use VEP to obtain the protein codon position of the variant.\n"
            "\n"
            "STEP 1: Is the variant in a well-established critical functional domain of this gene?\n"
            "  Assess using knowledge of the gene's protein structure:\n"
            "  - Active sites or catalytic residues\n"
            "  - Ligand-binding or substrate-binding domains\n"
            "  - Known mutational hotspots (positions with multiple independent P/LP variants)\n"
            "  - Well-characterized structural domains (kinase domain, RING finger, DNA-binding domain, etc.)\n"
            "  - YES → continue to Step 2.\n"
            "  - NO / uncertain → PM1 does NOT apply. Set applies=false. Stop.\n"
            "\n"
            "STEP 2: Is there known benign variation at this specific position or domain?\n"
            "  - YES (known benign variants at same codon) → PM1 does NOT apply. Set applies=false.\n"
            "  - NO  → PM1_Moderate APPLIES. Set applies=true.\n"
            "\n"
            "Be conservative — only apply PM1 when domain membership is well-established. "
            "Record the domain name, codon position, and reasoning in evidence."
        ),
        "strength_override": "moderate",
    },

    # ══════════════════════════════════════════════════════════════════════════
    # PHASE 3
    # ══════════════════════════════════════════════════════════════════════════

    "PVS1": {
        "criterion": "PVS1",
        "acmg_category": "Pathogenic",
        "strength": "very_strong",
        "automation": "fully_automatable",
        "tool": "vep",
        "phase": 3,
        "depends_on": [],
        "variant_types": ["frameshift", "nonsense", "splice_site", "start_lost"],
        "description": (
            "Null variant (nonsense, frameshift, canonical +/−1 or 2 splice sites, initiation codon, "
            "single or multi-exon deletion) in a gene where loss of function (LOF) is a known mechanism of disease. "
            "Standard ACMG PVS1 decision tree (no gene-specific codon boundaries). "
            "NMD is predicted when the premature termination codon (PTC) is NOT in the last exon and "
            "NOT within 50–55 nt of the last exon-exon junction. "
            "Caveats: do not apply to genes where LOF is NOT the disease mechanism (e.g. GFAP, MYH7)."
        ),
        "threshold": "LOF consequence in gene with established LOF disease mechanism",
        "instructions": (
            "Use VEP to determine variant consequence and protein codon position.\n"
            "\n"
            "PREREQUISITE: Is LOF a known disease mechanism for this gene?\n"
            "  - NO (e.g. dominant negative, gain-of-function) → PVS1 does NOT apply. Set applies=false. Stop.\n"
            "  - UNCERTAIN → apply PVS1 with caution; note caveat in evidence.\n"
            "  - YES → continue.\n"
            "\n"
            "NONSENSE OR FRAMESHIFT:\n"
            "  NMD is predicted if the PTC is NOT in the last exon and NOT within 50–55 nt upstream\n"
            "  of the last exon-exon junction.\n"
            "  - NMD predicted → PVS1 (Very Strong). Set applied_strength=very_strong.\n"
            "  - NMD NOT predicted (3'-terminal / last exon variant):\n"
            "      * Truncated region is critical to protein function → PVS1_Strong. applied_strength=strong.\n"
            "      * Role of region unknown AND variant removes <10% of protein → PVS1_Moderate. applied_strength=moderate.\n"
            "      * Otherwise → PVS1 does NOT apply. Set applies=false.\n"
            "\n"
            "CANONICAL SPLICE SITES (+/−1, 2):\n"
            "  - Exon skipping predicted, disrupts reading frame, NMD predicted → PVS1 (Very Strong).\n"
            "  - Exon skipping predicted, disrupts reading frame, NMD NOT predicted:\n"
            "      * Truncated region critical → PVS1_Strong.\n"
            "      * Role unknown AND <10% protein removed → PVS1_Moderate.\n"
            "  - Exon skipping preserves reading frame:\n"
            "      * Region critical → PVS1_Strong. Otherwise → PVS1_Moderate.\n"
            "\n"
            "INITIATION CODON (start_lost):\n"
            "  - No known alternative start codon → PVS1_Moderate. Set applied_strength=moderate.\n"
            "  - Known downstream alternative start codon → lower strength or not applicable.\n"
            "\n"
            "Record variant consequence, codon position, NMD prediction, and final applied_strength."
        ),
        "strength_override": None,
    },

    "PM5": {
        "criterion": "PM5",
        "acmg_category": "Pathogenic",
        "strength": "moderate",
        "automation": "partially_automatable",
        "tool": "erepo",
        "phase": 3,
        "depends_on": ["PM1"],
        "variant_types": ["missense"],
        "description": (
            "Novel missense change at an amino acid residue where a different missense change "
            "determined to be pathogenic has been seen before. ACMG Moderate strength. "
            "Reference variants must be P/LP from a reputable source "
            "(expert panel, ClinVar 2+ star review, published VCEP classification). "
            "Cannot combine PM5_Strong with PM1."
        ),
        "threshold": ">=1 different P/LP missense at same codon from a reputable source",
        "instructions": (
            "Search ClinGen ERepo and ClinVar for variants at the same amino acid position with different substitutions.\n"
            "\n"
            "STEP 1: Are there P/LP-classified missense variants at the same codon with a DIFFERENT amino acid change?\n"
            "  - NO  → PM5 does NOT apply. Set applies=false. Stop.\n"
            "  - YES → continue to Step 2.\n"
            "\n"
            "STEP 2: Count qualifying variants (different substitution, same codon, P/LP, reputable source):\n"
            "  - >=2 different P/LP missense at same codon → PM5_Strong. Set applied_strength=strong.\n"
            "    RULE: do NOT combine PM5_Strong with PM1. If PM1 also applies, downgrade PM5 to Moderate.\n"
            "  - 1 different P/LP missense at same codon → PM5_Moderate. Set applied_strength=moderate.\n"
            "\n"
            "STEP 3: Could the query variant affect splicing rather than the amino acid?\n"
            "  - YES → PM5 may not be appropriate; note caveat in evidence.\n"
            "\n"
            "Record matched variant(s), classifications, amino acid changes, and source in evidence."
        ),
        "strength_override": None,
    },

    # ══════════════════════════════════════════════════════════════════════════
    # PHASE 4 — no dependencies
    # ══════════════════════════════════════════════════════════════════════════

    "PS1": {
        "criterion": "PS1",
        "acmg_category": "Pathogenic",
        "strength": "strong",
        "automation": "partially_automatable",
        "tool": "erepo",
        "phase": 4,
        "depends_on": [],
        "variant_types": ["missense"],
        "description": (
            "Same amino acid change as a previously established pathogenic variant regardless of nucleotide change. "
            "ACMG Strong strength. Reference variant must be P/LP from a reputable source. "
            "Caveat: beware of changes that impact splicing rather than the amino acid."
        ),
        "threshold": "Identical amino acid change, P/LP from a reputable source",
        "instructions": (
            "Search for variants producing the same amino acid change (regardless of nucleotide change).\n"
            "\n"
            "STEP 1: Does a P/LP-classified entry exist with the same amino acid change?\n"
            "  - NO  → PS1 does NOT apply. Set applies=false. Stop.\n"
            "  - YES → continue to Step 2.\n"
            "\n"
            "STEP 2: Is the source reputable (expert panel, 2+ star ClinVar, published VCEP)?\n"
            "  - NO  → PS1 does NOT apply. Set applies=false. Stop.\n"
            "  - YES → continue to Step 3.\n"
            "\n"
            "STEP 3: Could the query variant affect splicing rather than the amino acid?\n"
            "  - YES → PS1 NOT appropriate. Set applies=false.\n"
            "  - NO  → PS1 APPLIES. Set applies=true, applied_strength=strong.\n"
            "\n"
            "Record matched variant, classification, source, and amino acid change in evidence."
        ),
        "strength_override": "strong",
    },

    "PM4": {
        "criterion": "PM4",
        "acmg_category": "Pathogenic",
        "strength": "moderate",
        "automation": "fully_automatable",
        "tool": "vep",
        "phase": 4,
        "depends_on": [],
        "variant_types": ["inframe_insertion", "inframe_deletion", "stop_lost"],
        "description": (
            "Protein length changes due to in-frame deletions/insertions in a non-repeat region "
            "or stop-loss variants. ACMG Moderate strength."
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
            "  - YES → PM4 does NOT apply (BP3 may apply instead). Set applies=false.\n"
            "  - NO  → PM4_Moderate APPLIES. Set applies=true.\n"
            "\n"
            "Record VEP consequence and repeat region status in evidence."
        ),
        "strength_override": "moderate",
    },

    "PP3": {
        "criterion": "PP3",
        "acmg_category": "Pathogenic",
        "strength": "supporting",
        "automation": "fully_automatable",
        "tool": "revel_spliceai",
        "phase": 4,
        "depends_on": [],
        "variant_types": ["missense", "synonymous", "intronic", "splice_region", "splice_site"],
        "description": (
            "Multiple lines of computational evidence support a deleterious effect. "
            "ClinGen SVI calibrated thresholds: REVEL >= 0.644 (missense) OR SpliceAI >= 0.2. "
            "PP3 can be used only once per variant evaluation."
        ),
        "threshold": "Missense: REVEL >= 0.644 OR SpliceAI >= 0.2 | Synonymous/intronic: SpliceAI >= 0.2",
        "instructions": (
            "Fetch REVEL score and all four SpliceAI delta scores (DS_AG, DS_AL, DS_DG, DS_DL).\n"
            "PP3 can be used only once per variant evaluation.\n"
            "\n"
            "BRANCH A — Missense variant:\n"
            "  STEP 1: Is REVEL score >= 0.644?\n"
            "    - YES → PP3 APPLIES. Set applies=true. Record REVEL score as trigger. Stop.\n"
            "    - NO  → continue to Step 2.\n"
            "  STEP 2: Is ANY SpliceAI delta score >= 0.2?\n"
            "    - YES → PP3 APPLIES. Set applies=true. Record which score triggered.\n"
            "    - NO  → PP3 does NOT apply. Set applies=false.\n"
            "\n"
            "BRANCH B — Synonymous or intronic variant:\n"
            "  STEP 1: Is ANY SpliceAI delta score >= 0.2?\n"
            "    - YES → PP3 APPLIES. Set applies=true.\n"
            "    - NO  → PP3 does NOT apply. Set applies=false.\n"
            "\n"
            "Record exact scores and which threshold triggered in evidence."
        ),
        "strength_override": "supporting",
    },

    "PP5": {
        "criterion": "PP5",
        "acmg_category": "Pathogenic",
        "strength": "supporting",
        "automation": "partially_automatable",
        "tool": "clinvar",
        "phase": 4,
        "depends_on": [],
        "description": (
            "Reputable source recently reports the variant as pathogenic, but evidence is not available "
            "for independent evaluation. ACMG Supporting strength. "
            "Reputable sources: ClinGen expert panels, ClinVar 2+ star submissions, published VCEP classifications."
        ),
        "threshold": "Exact variant classified P/LP by a reputable source in ClinVar (star_rating >= 2)",
        "instructions": (
            "Search ClinVar for the exact variant's aggregate classification.\n"
            "NOTE: the evidence will contain 'found', 'classification', 'review_status', "
            "'star_rating' (0–4), and 'reputable_source' (True if star_rating >= 2).\n"
            "\n"
            "STEP 1: Is found == true?\n"
            "  - NO  → PP5 does NOT apply. Set applies=false. Stop.\n"
            "  - YES → continue to Step 2.\n"
            "\n"
            "STEP 2: Is classification 'Pathogenic' or 'Likely pathogenic'?\n"
            "  - NO  → PP5 does NOT apply. Set applies=false. Stop.\n"
            "  - YES → continue to Step 3.\n"
            "\n"
            "STEP 3: Is reputable_source == true (star_rating >= 2)?\n"
            "  - NO  (star_rating 0–1, single lab) → PP5 does NOT apply. Set applies=false.\n"
            "  - YES → PP5 APPLIES. Set applies=true.\n"
            "\n"
            "PP5 should not substitute for independent evaluation when evidence IS available. "
            "Record classification, review_status, and star_rating in evidence."
        ),
        "strength_override": "supporting",
    },

    "BP3": {
        "criterion": "BP3",
        "acmg_category": "Benign",
        "strength": "supporting",
        "automation": "fully_automatable",
        "tool": "vep",
        "phase": 4,
        "depends_on": [],
        "variant_types": ["inframe_insertion", "inframe_deletion"],
        "description": (
            "In-frame deletions/insertions in a repetitive region without a known function. "
            "ACMG Supporting benign strength. "
            "BP3 and PM4 are mutually exclusive for in-frame indels — BP3 applies in repeat regions, "
            "PM4 applies outside repeat regions."
        ),
        "threshold": "VEP consequence = inframe_insertion or inframe_deletion AND overlaps repeat region",
        "instructions": (
            "Use VEP to annotate the variant consequence and check for repeat region overlap.\n"
            "\n"
            "STEP 1: What is the VEP consequence?\n"
            "  - inframe_insertion or inframe_deletion → continue to Step 2.\n"
            "  - anything else → BP3 does NOT apply. Set applies=false. Stop.\n"
            "\n"
            "STEP 2: Does the variant overlap a repeat region?\n"
            "  - YES → BP3 APPLIES. Set applies=true.\n"
            "    Note: PM4 cannot also apply for this variant — BP3 and PM4 are mutually exclusive.\n"
            "  - NO  → BP3 does NOT apply (consider PM4 instead). Set applies=false.\n"
            "\n"
            "Record VEP consequence and repeat region status in evidence."
        ),
        "strength_override": "benign_supporting",
    },

    "BP4": {
        "criterion": "BP4",
        "acmg_category": "Benign",
        "strength": "supporting",
        "automation": "fully_automatable",
        "tool": "revel_spliceai",
        "phase": 4,
        "depends_on": [],
        "variant_types": ["missense", "synonymous", "intronic", "splice_region", "splice_site"],
        "description": (
            "Multiple lines of computational evidence suggest no impact on gene or gene product. "
            "ClinGen SVI calibrated thresholds: REVEL <= 0.290 AND SpliceAI <= 0.1 for missense. "
            "BP4 can be used only once per variant evaluation."
        ),
        "threshold": "Missense: REVEL <= 0.290 AND SpliceAI <= 0.1 | Synonymous/intronic: SpliceAI <= 0.1",
        "instructions": (
            "Fetch REVEL score and all four SpliceAI delta scores (DS_AG, DS_AL, DS_DG, DS_DL).\n"
            "BP4 can be used only once per variant evaluation.\n"
            "\n"
            "BRANCH A — Missense variant (BOTH conditions required — AND logic):\n"
            "  STEP 1: Is REVEL score <= 0.290?\n"
            "    - NO  → BP4 does NOT apply. Set applies=false. Stop.\n"
            "    - YES → continue to Step 2.\n"
            "  STEP 2: Are ALL four SpliceAI delta scores <= 0.1?\n"
            "    - NO  (any score > 0.1) → BP4 does NOT apply. Set applies=false.\n"
            "    - YES (all scores <= 0.1) → BP4 APPLIES. Set applies=true.\n"
            "\n"
            "BRANCH B — Synonymous or intronic variant (SpliceAI only):\n"
            "  STEP 1: Are ALL four SpliceAI delta scores <= 0.1?\n"
            "    - NO  → BP4 does NOT apply. Set applies=false.\n"
            "    - YES → BP4 APPLIES. Set applies=true.\n"
            "\n"
            "Record exact REVEL and SpliceAI scores in evidence."
        ),
        "strength_override": "benign_supporting",
    },

    "BP6": {
        "criterion": "BP6",
        "acmg_category": "Benign",
        "strength": "supporting",
        "automation": "partially_automatable",
        "tool": "clinvar",
        "phase": 4,
        "depends_on": [],
        "description": (
            "Reputable source recently reports the variant as benign, but evidence is not available "
            "for independent evaluation. ACMG Supporting benign strength. "
            "Reputable sources: ClinGen expert panels, ClinVar 2+ star submissions."
        ),
        "threshold": "Exact variant classified B/LB by a reputable source in ClinVar (star_rating >= 2)",
        "instructions": (
            "Search ClinVar for the exact variant's aggregate classification.\n"
            "NOTE: the evidence will contain 'found', 'classification', 'review_status', "
            "'star_rating' (0–4), and 'reputable_source' (True if star_rating >= 2).\n"
            "\n"
            "STEP 1: Is found == true?\n"
            "  - NO  → BP6 does NOT apply. Set applies=false. Stop.\n"
            "  - YES → continue to Step 2.\n"
            "\n"
            "STEP 2: Is classification 'Benign' or 'Likely benign'?\n"
            "  - NO  → BP6 does NOT apply. Set applies=false. Stop.\n"
            "  - YES → continue to Step 3.\n"
            "\n"
            "STEP 3: Is reputable_source == true (star_rating >= 2)?\n"
            "  - NO  (star_rating 0–1, single lab) → BP6 does NOT apply. Set applies=false.\n"
            "  - YES → BP6 APPLIES. Set applies=true.\n"
            "\n"
            "Record classification, review_status, and star_rating in evidence."
        ),
        "strength_override": "benign_supporting",
    },

    "BP7": {
        "criterion": "BP7",
        "acmg_category": "Benign",
        "strength": "supporting",
        "automation": "fully_automatable",
        "tool": "spliceai",
        "phase": 4,
        "depends_on": [],
        "variant_types": ["synonymous", "intronic"],
        "description": (
            "A synonymous (silent) variant for which splicing prediction algorithms predict no impact "
            "on the splice consensus sequence or creation of a new splice site, AND the nucleotide is "
            "not highly conserved. ACMG Supporting benign strength."
        ),
        "threshold": "Synonymous or intronic variant AND SpliceAI <= 0.1 for all four delta scores",
        "instructions": (
            "Fetch all four SpliceAI delta scores (DS_AG, DS_AL, DS_DG, DS_DL).\n"
            "BP7 applies to synonymous or intronic variants only.\n"
            "\n"
            "STEP 1: Are ALL four SpliceAI delta scores <= 0.1?\n"
            "  - YES → BP7 APPLIES. Set applies=true.\n"
            "  - NO  (any score > 0.1) → BP7 does NOT apply. Set applies=false.\n"
            "\n"
            "Note: also consider nucleotide conservation — high conservation at this position "
            "warrants additional caution even if SpliceAI is low.\n"
            "Record all four SpliceAI scores in evidence."
        ),
        "strength_override": "benign_supporting",
    },

    # ══════════════════════════════════════════════════════════════════════════
    # DEFERRED — require expert input, clinical records, or non-automatable data
    # ══════════════════════════════════════════════════════════════════════════

    "PS2": {
        "criterion": "PS2",
        "acmg_category": "Pathogenic",
        "strength": "strong",
        "automation": "not_automatable",
        "tool": None,
        "phase": 4,
        "depends_on": [],
        "description": (
            "De novo (both maternity and paternity confirmed) in a patient with the disease and no family history. "
            "ACMG Strong strength. Requires laboratory confirmation of parental identity."
        ),
        "threshold": "Confirmed de novo with maternity and paternity verified",
        "instructions": (
            "PS2 cannot be evaluated automatically. "
            "Requires confirmed parental testing to verify both maternity and paternity. "
            "Egg donation, surrogate motherhood, and embryo transfer errors must be excluded. "
            "Return applies=null, status=deferred, with explanation."
        ),
        "strength_override": "strong",
        "deferred": True,
    },

    "PS3": {
        "criterion": "PS3",
        "acmg_category": "Pathogenic",
        "strength": "strong",
        "automation": "not_automatable",
        "tool": None,
        "phase": 4,
        "depends_on": [],
        "description": (
            "Well-established in vitro or in vivo functional studies supportive of a damaging effect. "
            "ACMG Strong strength. Studies must be validated, reproducible, and robust in a "
            "clinical diagnostic laboratory setting."
        ),
        "threshold": None,
        "instructions": (
            "PS3 cannot be evaluated automatically. "
            "Requires reading and assessing published functional assay papers. "
            "Studies must be validated and reproducible. "
            "Return applies=null, status=deferred, with explanation."
        ),
        "strength_override": None,
        "deferred": True,
    },

    "PM3": {
        "criterion": "PM3",
        "acmg_category": "Pathogenic",
        "strength": "moderate",
        "automation": "not_automatable",
        "tool": None,
        "phase": 4,
        "depends_on": [],
        "description": (
            "For recessive disorders: detected in trans with a pathogenic variant. "
            "ACMG Moderate strength (upgradeable to Strong with multiple independent trans observations). "
            "Requires parental testing to confirm phase."
        ),
        "threshold": "Confirmed in trans with a P/LP variant (parental or read-based phase testing)",
        "instructions": (
            "PM3 cannot be evaluated automatically. "
            "Requires parental testing or read-based phasing to confirm the variant is in trans "
            "with a pathogenic variant. Applicable for recessive disorders only. "
            "Return applies=null, status=deferred, with explanation."
        ),
        "strength_override": None,
        "deferred": True,
    },

    "PM6": {
        "criterion": "PM6",
        "acmg_category": "Pathogenic",
        "strength": "moderate",
        "automation": "not_automatable",
        "tool": None,
        "phase": 4,
        "depends_on": [],
        "description": (
            "Assumed de novo, but without confirmation of paternity and maternity. "
            "ACMG Moderate strength. Weaker than PS2 due to unconfirmed parental identity."
        ),
        "threshold": "Apparent de novo without confirmed parental identity",
        "instructions": (
            "PM6 cannot be evaluated automatically. "
            "Requires clinical records showing apparent de novo status without confirmed parental identity. "
            "Return applies=null, status=deferred, with explanation."
        ),
        "strength_override": "moderate",
        "deferred": True,
    },

    "PP1": {
        "criterion": "PP1",
        "acmg_category": "Pathogenic",
        "strength": "supporting",
        "automation": "not_automatable",
        "tool": None,
        "phase": 4,
        "depends_on": [],
        "description": (
            "Co-segregation with disease in multiple affected family members in a gene definitively "
            "known to cause the disease. ACMG Supporting strength "
            "(upgradeable to Moderate or Strong with increasing segregation data)."
        ),
        "threshold": "Co-segregation in >=2 affected family members; more meioses → stronger evidence",
        "instructions": (
            "PP1 cannot be evaluated automatically. "
            "Requires confirmed family pedigree with affected/unaffected status. "
            "Strength increases with more informative meioses (PP1_Supporting → Moderate → Strong). "
            "Return applies=null, status=deferred, with explanation."
        ),
        "strength_override": None,
        "deferred": True,
    },

    "PP2": {
    "criterion": "PP2",
    "acmg_category": "Pathogenic",
    "strength": "supporting",
    "automation": "fully_automatable",
    "tool": "gnomad",
    "phase": 4,
    "depends_on": [],
    "variant_types": ["missense"],
    "description": (
        "Missense variant in a gene that has a low rate of benign missense variation and in which "
        "missense variants are a common mechanism of disease. ACMG 2015: Supporting strength. "
        "Determined by gnomAD gene-level missense constraint Z-score. "
        "Threshold: Z-score ≥ 3.09 (p < 0.001, one-tailed). Fully deterministic — no judgment needed."
    ),
    "threshold": "gnomAD gene missense Z-score ≥ 3.09",
    "instructions": (
        "Query gnomAD gene-level constraint for the gene symbol (not the variant).\n"
        "Retrieve the missense Z-score from the gnomAD constraint table.\n"
        "\n"
        "STEP 1: Is the gene missense Z-score >= 3.09?\n"
        "  - YES → PP2 APPLIES. Set applies=true, strength=supporting.\n"
        "  - NO  → PP2 does NOT apply. Set applies=false.\n"
        "\n"
        "Record the exact Z-score and gene symbol in evidence."
    ),
    "strength_override": "supporting",
},

    "PP4": {
        "criterion": "PP4",
        "acmg_category": "Pathogenic",
        "strength": "supporting",
        "automation": "not_automatable",
        "tool": None,
        "phase": 4,
        "depends_on": [],
        "description": (
            "Patient's phenotype or family history is highly specific for a disease with a single "
            "genetic etiology. ACMG Supporting strength."
        ),
        "threshold": "Phenotype highly specific for disease with single genetic etiology",
        "instructions": (
            "PP4 cannot be evaluated automatically. "
            "Requires clinical phenotype assessment and review of family history. "
            "Return applies=null, status=deferred, with explanation."
        ),
        "strength_override": "supporting",
        "deferred": True,
    },

    "BS3": {
        "criterion": "BS3",
        "acmg_category": "Benign",
        "strength": "strong",
        "automation": "not_automatable",
        "tool": None,
        "phase": 4,
        "depends_on": [],
        "description": (
            "Well-established in vitro or in vivo functional studies show no damaging effect on "
            "protein function or splicing. ACMG Strong benign strength."
        ),
        "threshold": None,
        "instructions": (
            "BS3 cannot be evaluated automatically. "
            "Requires reading and assessing published functional assay papers that demonstrate "
            "no damaging effect on protein function or splicing. "
            "Return applies=null, status=deferred, with explanation."
        ),
        "strength_override": "benign_strong",
        "deferred": True,
    },

    "BS4": {
        "criterion": "BS4",
        "acmg_category": "Benign",
        "strength": "strong",
        "automation": "not_automatable",
        "tool": None,
        "phase": 4,
        "depends_on": [],
        "description": (
            "Lack of segregation in affected members of a family. ACMG Strong benign strength. "
            "Caveat: phenocopies (e.g. cancer, epilepsy) can mimic lack of segregation; "
            "families may carry more than one pathogenic variant in dominant disorders."
        ),
        "threshold": "Variant absent in affected family members (with appropriate caveats for phenocopies)",
        "instructions": (
            "BS4 cannot be evaluated automatically. "
            "Requires family pedigree data with confirmed affected/unaffected status. "
            "Consider phenocopies and the possibility of multiple pathogenic variants. "
            "Return applies=null, status=deferred, with explanation."
        ),
        "strength_override": "benign_strong",
        "deferred": True,
    },

    "BP1": {
        "criterion": "BP1",
        "acmg_category": "Benign",
        "strength": "supporting",
        "automation": "partially_automatable",
        "tool": "gnomad_gene",
        "phase": 4,
        "depends_on": [],
        "variant_types": ["missense"],
        "description": (
            "Missense variant in a gene for which primarily truncating variants are known to cause disease. "
            "ACMG Supporting benign strength. "
            "Uses gnomAD gene-level constraint (pLI, LOEUF, oe_mis) to support the assessment of "
            "whether the gene's disease mechanism is primarily LOF/truncating, not missense."
        ),
        "threshold": "Gene primarily causes disease via truncating/LOF variants, not missense",
        "instructions": (
            "Fetch gene-level constraint data from gnomAD for the gene of interest.\n"
            "The evidence will contain 'mis_z', 'pLI', 'oe_lof_upper', 'oe_mis', and '_computed.verdicts'.\n"
            "\n"
            "IMPORTANT: Use the '_computed.verdicts' field for the constraint profile. "
            "The final BP1 decision requires clinical knowledge of the gene's disease mechanism.\n"
            "\n"
            "STEP 1: Read the constraint profile from '_computed.verdicts'.\n"
            "  - Note pLI, LOEUF (oe_lof_upper), and oe_mis values.\n"
            "\n"
            "STEP 2: Use your knowledge of the gene's disease mechanism.\n"
            "  - If the gene is known to cause disease PRIMARILY via truncating/LOF variants "
            "(frameshift, nonsense, splice-disrupting variants dominate the pathogenic spectrum) "
            "AND missense variants are rarely pathogenic in this gene → BP1 APPLIES. Set applies=true.\n"
            "  - If missense variants are also a common pathogenic mechanism → BP1 does NOT apply.\n"
            "  - Constraint hint from gnomAD:\n"
            "    * High pLI (>=0.9) and low LOEUF (<=0.35) → gene is LOF-intolerant → LOF likely causes disease\n"
            "    * High oe_mis (>=0.8) → missense variants relatively tolerated in healthy population\n"
            "    These support BP1 only when combined with literature evidence that LOF is the primary mechanism.\n"
            "\n"
            "STEP 3: If the gene causes disease via BOTH missense AND LOF mechanisms → BP1 does NOT apply.\n"
            "\n"
            "Record pLI, LOEUF, oe_mis values and disease mechanism rationale in evidence."
        ),
        "strength_override": "benign_supporting",
    },

    "BP2": {
        "criterion": "BP2",
        "acmg_category": "Benign",
        "strength": "supporting",
        "automation": "not_automatable",
        "tool": None,
        "phase": 4,
        "depends_on": [],
        "description": (
            "Observed in trans with a pathogenic variant for a fully penetrant dominant gene/disorder; "
            "or observed in cis with a pathogenic variant in any inheritance pattern. "
            "ACMG Supporting benign strength. Requires phase testing."
        ),
        "threshold": "Confirmed in trans with P/LP variant (dominant) or in cis with P/LP variant (any)",
        "instructions": (
            "BP2 cannot be evaluated automatically. "
            "Requires patient-level phasing data (parental testing or read-based phasing). "
            "Return applies=null, status=deferred, with explanation."
        ),
        "strength_override": "benign_supporting",
        "deferred": True,
    },

    "BP5": {
        "criterion": "BP5",
        "acmg_category": "Benign",
        "strength": "supporting",
        "automation": "not_automatable",
        "tool": None,
        "phase": 4,
        "depends_on": [],
        "description": (
            "Variant found in a case with an alternate molecular basis for disease. "
            "ACMG Supporting benign strength. Requires identification of an alternate causative variant."
        ),
        "threshold": "Alternate causative variant identified in the same patient",
        "instructions": (
            "BP5 cannot be evaluated automatically. "
            "Requires clinical/molecular data showing an alternate causative variant in the patient. "
            "Return applies=null, status=deferred, with explanation."
        ),
        "strength_override": "benign_supporting",
        "deferred": True,
    },

    # ══════════════════════════════════════════════════════════════════════════
    # SCORING — ACMG/AMP 2015 standard combining rules
    # Source: Richards et al. Genet Med 2015;17(5):405–424 (Table 5)
    # ══════════════════════════════════════════════════════════════════════════

    "SCORING": {
        "criterion": "SCORING",

        # Fixed-strength criteria: key → strength bucket.
        # Variable-strength criteria (PVS1, PS4, PM5, PP1, PS2 upgraded, PM3 upgraded)
        # are NOT listed here — they use applied_strength from the task agent.
        "fixed_strengths": {
            "PM2":  "moderate",
            "PM1":  "moderate",
            "PM4":  "moderate",
            "PM6":  "moderate",
            "PS1":  "strong",
            "PS2":  "strong",
            "PP3":  "supporting",
            "PP4":  "supporting",
            "PP5":  "supporting",
            "BA1":  "benign_stand_alone",
            "BS1":  "benign_strong",
            "BS2":  "benign_strong",
            "BS3":  "benign_strong",
            "BS4":  "benign_strong",
            "BP1":  "benign_supporting",
            "BP2":  "benign_supporting",
            "BP3":  "benign_supporting",
            "BP4":  "benign_supporting",
            "BP5":  "benign_supporting",
            "BP6":  "benign_supporting",
            "BP7":  "benign_supporting",
        },

        "variable_strength_map": {
            "very_strong":       "very_strong",
            "strong":            "strong",
            "moderate":          "moderate",
            "supporting":        "supporting",
            "benign_strong":     "benign_strong",
            "benign_supporting": "benign_supporting",
        },

        "incompatible_combinations": [
            {
                "criteria":   ["PM1", "PM5"],
                "condition":  "PM5 applied_strength == strong",
                "action":     "downgrade",
                "target":     "PM5",
                "new_strength": "moderate",
                "note": "PM1 and PM5_Strong cannot be combined — PM5 is downgraded to Moderate",
            },
        ],

        # Standard ACMG/AMP 2015 pathogenic combining rules (Table 5)
        "pathogenic_rules": [
            {"vs": 1, "s": 1,                     "label": "PVS1 + ≥1 Strong"},
            {"vs": 1, "m": 2,                     "label": "PVS1 + ≥2 Moderate"},
            {"vs": 1, "m": 1, "sup": 1,           "label": "PVS1 + 1 Moderate + 1 Supporting"},
            {"vs": 1, "sup": 2,                   "label": "PVS1 + ≥2 Supporting"},
            {"s": 2,                               "label": "≥2 Strong"},
            {"s": 1, "m": 3,                       "label": "1 Strong + ≥3 Moderate"},
            {"s": 1, "m": 2, "sup": 2,            "label": "1 Strong + 2 Moderate + ≥2 Supporting"},
            {"s": 1, "m": 1, "sup": 4,            "label": "1 Strong + 1 Moderate + ≥4 Supporting"},
        ],

        "likely_pathogenic_rules": [
            {"vs": 1, "m": 1,                     "label": "PVS1 + 1 Moderate"},
            {"vs": 1, "sup": 1,                   "label": "PVS1 + 1 Supporting"},
            {"s": 1, "m": 2,                       "label": "1 Strong + 2 Moderate"},
            {"s": 1, "m": 1,                       "label": "1 Strong + 1 Moderate"},
            {"s": 1, "sup": 2,                    "label": "1 Strong + ≥2 Supporting"},
            {"m": 3,                               "label": "≥3 Moderate"},
            {"m": 2, "sup": 2,                    "label": "2 Moderate + ≥2 Supporting"},
            {"m": 1, "sup": 4,                    "label": "1 Moderate + ≥4 Supporting"},
        ],

        "benign_rules": [
            {"ba": 1,          "label": "BA1 stand-alone"},
            {"bs": 2,          "label": "≥2 Strong benign"},
        ],

        "likely_benign_rules": [
            {"bs": 1, "bsup": 1, "label": "1 Strong + 1 Supporting benign"},
            {"bsup": 2,          "label": "≥2 Supporting benign"},
        ],
    },
}


ACMG_EXCLUDED_CRITERIA = {}


def query(criterion: str, gene: str = None, disease: str = None) -> dict | None:
    """
    Retrieve the PlanRAG entry for a given ACMG criterion.

    Parameters
    ----------
    criterion : str
        Criterion key (e.g. "PM1", "PM2_SUPPORTING") or display name (e.g. "PM2_Supporting").
    gene : str | None
        Gene symbol (e.g. "ACVRL1", "ENG"). When provided and the entry has a
        gene_data dict, the gene-specific sub-dict is merged into the returned entry.
        When None, defaults to the first gene in gene_data (ACVRL1) for backward compatibility.
    disease : str | None
        Disease name entered by the user. If provided and NOT in VCEP_DISEASES,
        routes to ACMG_PLANRAG_DB (generic ACMG/AMP 2015 criteria).
        If None or a VCEP disease, routes to PLANRAG_DB (HHT VCEP) for backward compatibility.

    Returns
    -------
    dict | None
        A shallow copy of the planrag entry with gene-specific fields merged in,
        or None if the criterion is not found.
    """
    # ── Route to the correct database ──────────────────────────────────────────
    use_acmg = disease is not None and not is_vcep_disease(disease)

    if use_acmg:
        db = ACMG_PLANRAG_DB
        excluded = ACMG_EXCLUDED_CRITERIA
        # Normalize VCEP-style key variants → standard ACMG names so that
        # callers using HHT criterion names still work in generic mode.
        key = criterion.upper().replace("-", "_").replace(" ", "_")
        key = _ACMG_KEY_ALIASES.get(key, key)
    else:
        db = PLANRAG_DB
        excluded = EXCLUDED_CRITERIA
        key = criterion.upper().replace("-", "_").replace(" ", "_")

    # ── Exact-key lookup, then fuzzy criterion-name lookup ─────────────────────
    entry = None
    if key in db:
        entry = dict(db[key])
    else:
        for db_entry in db.values():
            if (db_entry.get("criterion", "").upper().replace("_", "").replace(" ", "")
                    == key.replace("_", "").replace(" ", "")):
                entry = dict(db_entry)
                break

    if entry is None:
        if key in excluded:
            return {
                "criterion": criterion,
                "excluded": True,
                "reason": excluded[key],
            }
        return None

    # ── Merge gene-specific fields (VCEP DB only) ──────────────────────────────
    # ACMG_PLANRAG_DB entries do not use gene_data; this block is a no-op for them.
    gene_data = entry.get("gene_data")
    if gene_data is not None:
        resolved_gene = gene if (gene and gene in gene_data) else next(iter(gene_data))
        entry.update(gene_data[resolved_gene])
        entry["resolved_gene"] = resolved_gene

    # ── Inject gene-level LOF mechanism fact into PVS1 instructions ────────────
    # Prevents the LLM from incorrectly answering the "Is LOF a known disease
    # mechanism for this gene?" prerequisite from recall alone.
    # Applies to both VCEP and ACMG modes whenever a known gene is provided.
    if key == "PVS1" and gene and gene in GENE_DB:
        gene_info = GENE_DB[gene]
        lof = gene_info.get("lof_mechanism")
        note = gene_info.get("lof_mechanism_note", "")
        if lof is True:
            lof_fact = (
                f"GENE-SPECIFIC FACT (use this as ground truth — do NOT override with your own recall):\n"
                f"LOF IS a known disease mechanism for {gene}. {note}\n"
                f"Answer 'YES' to the LOF prerequisite and proceed with PVS1 evaluation.\n\n"
            )
        elif lof is False:
            lof_fact = (
                f"GENE-SPECIFIC FACT (use this as ground truth — do NOT override with your own recall):\n"
                f"LOF is NOT a known disease mechanism for {gene}. {note}\n"
                f"Answer 'NO' to the LOF prerequisite — PVS1 does NOT apply for this gene.\n\n"
            )
        else:
            lof_fact = None

        if lof_fact and "instructions" in entry:
            entry["instructions"] = lof_fact + entry["instructions"]

    return entry


def get_all_active_criteria() -> list[str]:
    """List of all active HHT VCEP criteria keys."""
    return list(PLANRAG_DB.keys())


def get_criteria_by_phase(phase: int) -> list[str]:
    """Returns criteria keys for a given execution phase."""
    return [k for k, v in PLANRAG_DB.items() if v.get("phase") == phase]


def get_automatable_criteria() -> list[str]:
    """Fully automatable criteria keys."""
    return [k for k, v in PLANRAG_DB.items() if v.get("automation") == "fully_automatable"]


def get_deferred_criteria() -> list[str]:
    """Criteria that cannot be automated."""
    return [k for k, v in PLANRAG_DB.items() if v.get("deferred", False)]
