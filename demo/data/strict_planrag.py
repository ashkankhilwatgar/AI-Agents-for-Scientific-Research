# PlanRAG database — HHT VCEP criteria for ACVRL1
# Source of truth: ClinGen CSpec Registry GN135 v1.1.0 (released 3/20/2024)
# https://cspec.genome.network/cspec/ui/svi/doc/GN135
#
# STRICT MODE: every field below contains only content traceable to the CSpec PDF.
# No pipeline operational rules, no inferred guardrails, no implementation guidance.
# All operational decisions (ClinVar star thresholds, conflict-handling rules,
# tool choices, etc.) belong elsewhere — Judge agent prompts, Scoring agent logic,
# or a separate pipeline_rules config — not here.

PLANRAG_DB = {

    # ──────────────────────────────────────────────────────────────────────────
    # PATHOGENIC CRITERIA — ACTIVE
    # ──────────────────────────────────────────────────────────────────────────

    "PVS1": {
        "criterion": "PVS1",
        "acmg_category": "Pathogenic",
        "strength_levels_defined": ["very_strong", "strong", "moderate"],
        "acmg_summary": (
            "Null variant (nonsense, frameshift, canonical +/-1 or 2 splice sites, "
            "initiation codon, single or multi-exon deletion) in a gene where loss of function "
            "is a known mechanism of disease."
        ),
        "vcep_specifications": "Use ACVRL1 PVS1 Decision Tree (see attachments).",
        "vcep_strength_rules": {
            "very_strong": "Use ACVRL1 PVS1 Decision Tree (Modification Type: Gene-specific, Strength).",
            "strong": "Use ACVRL1 PVS1 Decision Tree (Modification Type: Gene-specific, Strength).",
            "moderate": "Use ACVRL1 PVS1 Decision Tree (Modification Type: Gene-specific, Strength).",
        },
        "decision_tree_summary": (
            "From the ACVRL1 PVS1 Decision Tree image:\n"
            "Codon thresholds: 442 (NMD boundary), 490 (critical region boundary).\n"
            "\n"
            "Nonsense or Frameshift:\n"
            "  - Predicted NMD (ACVRL1 <=codon 442) → PVS1\n"
            "  - Not predicted NMD (ACVRL1 >codon 442):\n"
            "      * Truncated/altered region critical to protein function (ACVRL1 <=codon 490) → PVS1_Strong\n"
            "      * Role of region unknown AND variant removes <10% of protein → PVS1_Moderate\n"
            "\n"
            "GT-AG +/-1,2 splice sites:\n"
            "  - Exon skipping/cryptic splice disrupts reading frame, predicted NMD (<=codon 442) → PVS1\n"
            "  - Exon skipping/cryptic splice disrupts reading frame, NOT predicted NMD (>codon 442):\n"
            "      * Region critical (<=codon 490; see also PM1 regions) → PVS1_Strong\n"
            "      * Role unknown AND removes <10% of protein → PVS1_Moderate\n"
            "  - Exon skipping/cryptic splice preserves reading frame:\n"
            "      * Region critical (<=codon 490) → PVS1_Strong\n"
            "      * Role unknown AND removes <10% of protein → PVS1_Moderate\n"
            "\n"
            "Deletion (single exon to full gene):\n"
            "  - Full gene deletion → PVS1\n"
            "  - Single/multi-exon deletion disrupts reading frame, predicted NMD, exon in "
            "biologically-relevant transcript → PVS1\n"
            "  - Single/multi-exon deletion disrupts reading frame, NOT predicted NMD:\n"
            "      * Region critical (<=codon 490) → PVS1_Strong\n"
            "      * Role unknown AND removes <10% of protein → PVS1_Moderate\n"
            "  - Single/multi-exon deletion preserves reading frame:\n"
            "      * Region critical (<=codon 490) → PVS1_Strong\n"
            "\n"
            "Duplication (>=1 exon, fully within gene):\n"
            "  - Proven in tandem AND reading frame disrupted AND NMD predicted → PVS1\n"
            "  - Proven in tandem AND no/unknown impact on reading frame and NMD → N/A\n"
            "  - Presumed in tandem AND reading frame presumed disrupted AND NMD predicted → PVS1_Strong\n"
            "  - Proven NOT in tandem → N/A\n"
            "\n"
            "Initiation Codon:\n"
            "  - No known alternative start codon in other transcripts → PVS1_Moderate (ACVRL1)"
        ),
        "caveats_from_acmg": [
            "Beware of genes where LOF is not a known disease mechanism (e.g. GFAP, MYH7).",
            "Use caution interpreting LOF variants at the extreme 3' end of a gene.",
            "Use caution with splice variants predicted to lead to exon skipping but leave the remainder of the protein intact.",
            "Use caution in the presence of multiple transcripts.",
        ],
    },

    "PS1": {
        "criterion": "PS1",
        "acmg_category": "Pathogenic",
        "strength_levels_defined": ["strong"],
        "acmg_summary": (
            "Same amino acid change as a previously established pathogenic variant regardless of nucleotide change. "
            "Example: Val->Leu caused by either G>C or G>T in the same codon."
        ),
        "vcep_specifications": "No modification. Use as applicable.",
        "vcep_strength_rules": {
            "strong": (
                "Same amino acid change as a previously established pathogenic variant regardless "
                "of nucleotide change. Example: Val->Leu caused by either G>C or G>T in the same codon. "
                "(Modification Type: No change)"
            ),
        },
        "caveats_from_acmg": [
            "Beware of changes that impact splicing rather than at the amino acid/protein level.",
        ],
    },

    "PS3": {
        "criterion": "PS3",
        "acmg_category": "Pathogenic",
        "strength_levels_defined": ["strong", "moderate", "supporting"],
        "acmg_summary": (
            "Well-established in vitro or in vivo functional studies supportive of a damaging effect "
            "on the gene or gene product."
        ),
        "acmg_note": (
            "Functional studies that have been validated and shown to be reproducible and robust in a "
            "clinical diagnostic laboratory setting are considered the most well-established."
        ),
        "vcep_specifications": (
            "HHT assays can be used as supporting evidence and bumped up to moderate/strong criteria "
            "if multiple different functional assays are concordant."
        ),
        "vcep_strength_rules": {
            "strong": (
                "mRNA splicing assays can be used as strong functional evidence. "
                "Note: level of evidence used may differ depending on whether the abnormal transcript "
                "is in-frame or out-of-frame, and whether there is complete or incomplete splicing impact. "
                "Do not use PS3 for splice variants that meet PVS1. "
                "(Modification Type: Disease-specific, Strength)"
            ),
            "moderate": (
                "See PS3_Supporting and Instructions below. "
                "(Modification Type: Disease-specific, Strength)"
            ),
            "supporting": (
                "Protein expression assays: Metabolic label & IP, WB & FACS HUVECs/BOECs, "
                "FACS activated monocytes, cDNA transfect, WB & ML HEK293T/COS/NIH3T3, "
                "cDNA transfect & luciferase HepG2. "
                "Note: Decreased protein expression can be used as supporting pathogenic evidence if "
                "experiment was not done in a single assay, and the corresponding densitometry of "
                "western blot reflects the conclusion drawn. "
                "Intracellular signaling assays: BRE/CAGA-luciferase, Gal4 Smad1/Smad3 for "
                "TGF-beta/BMP9 signaling. "
                "Binding assays: BMP9 binding, transcription factor Sp1, BMP9 protein-protein interaction (BLI). "
                "Subcellular protein localization. "
                "Morphology: Morphology & actin cytoskeleton, tubulogenesis. "
                "Somatic variant 2nd hit: In vivo evidence can be obtained as supporting functional "
                "evidence by identification of somatic variants in telangiectases biopsies using NGS, "
                "suggesting a second-hit mechanism leading to biallelic LOF (PMID: 31630786). "
                "(Modification Type: Disease-specific, Strength)"
            ),
        },
    },

    "PS4": {
        "criterion": "PS4",
        "acmg_category": "Pathogenic",
        "strength_levels_defined": ["strong", "moderate", "supporting"],
        "acmg_summary": (
            "The prevalence of the variant in affected individuals is significantly increased "
            "compared to the prevalence in controls."
        ),
        "acmg_notes": [
            "Note 1: Relative risk (RR) or odds ratio (OR), as obtained from case-control studies, "
            "is >5.0 and the confidence interval around the estimate of RR or OR does not include 1.0.",
            "Note 2: In instances of very rare variants where case-control studies may not reach "
            "statistical significance, the prior observation of the variant in multiple unrelated "
            "patients with the same phenotype, and its absence in controls, may be used as moderate "
            "level of evidence.",
        ],
        "vcep_specifications": (
            "Variant must also meet PM2_Supporting. "
            "See HHT phenotype document in attachments for phenotype requirements."
        ),
        "vcep_strength_rules": {
            "strong": "4+ probands with phenotype consistent with HHT. (Modification Type: Disease-specific)",
            "moderate": "2-3 probands with phenotype consistent with HHT. (Modification Type: Disease-specific)",
            "supporting": "1 proband with phenotype consistent with HHT. (Modification Type: Disease-specific)",
        },
    },

    "PM1": {
        "criterion": "PM1",
        "acmg_category": "Pathogenic",
        "strength_levels_defined": ["moderate"],
        "acmg_summary": (
            "Located in a mutational hot spot and/or critical and well-established functional domain "
            "(e.g. active site of an enzyme) without benign variation."
        ),
        "vcep_specifications": (
            "Note: If the variant falls within a PM1 region, do not use PM1 with PM5_Strong. "
            "PM1 can still be combined with PM5."
        ),
        "vcep_strength_rules": {
            "moderate": (
                "Apply if variant is located in a critical residue. ACVRL1 critical residues: "
                "glycine-rich loop: G209-V216; "
                "phosphate anchor: K229; "
                "C-helix E pairing the phosphate anchor: E242; "
                "catalytic loop: R329-N335; "
                "metal-binding loop: D348-L351; "
                "BMP10 interaction cluster: His40, Val54, Val56, Arg57, Glu58, Glu59, His66, Asn71, "
                "Leu72, His73, Glu75, Leu76, Arg78, Gly79, Arg80, Thr82, Glu83, Phe84, Val85, His87. "
                "(Modification Type: Gene-specific)"
            ),
        },
    },

    "PM2_SUPPORTING": {
        "criterion": "PM2_Supporting",
        "acmg_category": "Pathogenic",
        "strength_levels_defined": ["supporting"],
        "acmg_summary": (
            "Absent from controls (or at extremely low frequency if recessive) in Exome Sequencing Project, "
            "1000 Genomes or Exome Aggregation Consortium."
        ),
        "vcep_specifications": None,
        "vcep_strength_rules": {
            "supporting": (
                "<6 total alleles in gnomAD or <0.00004 (0.004%) in gnomAD subpopulations. "
                "(Modification Type: Disease-specific, Strength)"
            ),
        },
        "caveats_from_acmg": [
            "Population data for indels may be poorly called by next generation sequencing.",
        ],
    },

    "PM4": {
        "criterion": "PM4",
        "acmg_category": "Pathogenic",
        "strength_levels_defined": ["moderate"],
        "acmg_summary": (
            "Protein length changes due to in-frame deletions/insertions in a non-repeat region or "
            "stop-loss variants."
        ),
        "vcep_specifications": "No modification. Use as applicable.",
        "vcep_strength_rules": {
            "moderate": (
                "Protein length changes due to in-frame deletions/insertions in a non-repeat region "
                "or stop-loss variants. (Modification Type: None)"
            ),
        },
    },

    "PM5": {
        "criterion": "PM5",
        "acmg_category": "Pathogenic",
        "strength_levels_defined": ["strong", "moderate"],
        "acmg_summary": (
            "Novel missense change at an amino acid residue where a different missense change determined "
            "to be pathogenic has been seen before. Example: Arg156His is pathogenic; now you observe Arg156Cys."
        ),
        "vcep_specifications": None,
        "vcep_strength_rules": {
            "strong": (
                ">=2 different missense changes at same codon have been determined to be likely "
                "pathogenic or pathogenic based on HHT VCEP rules. "
                "(Modification Type: Disease-specific, Strength)"
            ),
            "moderate": (
                "A different missense change at same codon has been determined to be likely "
                "pathogenic or pathogenic based on HHT VCEP rules. "
                "(Modification Type: Disease-specific, Strength)"
            ),
        },
        "caveats_from_acmg": [
            "Beware of changes that impact splicing rather than at the amino acid/protein level.",
        ],
    },

    "PP1": {
        "criterion": "PP1",
        "acmg_category": "Pathogenic",
        "strength_levels_defined": ["strong", "moderate", "supporting"],
        "acmg_summary": (
            "Co-segregation with disease in multiple affected family members in a gene definitively "
            "known to cause the disease."
        ),
        "acmg_note": "May be used as stronger evidence with increasing segregation data.",
        "vcep_specifications": (
            "See HHT phenotype document in attachments for assignment of affected/unaffected status "
            "for purpose of inclusion in cosegregation study."
        ),
        "vcep_strength_rules": {
            "strong": "5+ meioses (1/32 likelihood). (Modification Type: Disease-specific, Strength)",
            "moderate": "4 meioses (1/16 likelihood). (Modification Type: Disease-specific, Strength)",
            "supporting": "3 meioses (1/8 likelihood). (Modification Type: Disease-specific, Strength)",
        },
    },

    "PP3": {
        "criterion": "PP3",
        "acmg_category": "Pathogenic",
        "strength_levels_defined": ["supporting"],
        "acmg_summary": (
            "Multiple lines of computational evidence support a deleterious effect on the gene or "
            "gene product (conservation, evolutionary, splicing impact, etc.)."
        ),
        "acmg_caveat": (
            "As many in silico algorithms use the same or very similar input for their predictions, "
            "each algorithm should not be counted as an independent criterion. PP3 can be used only "
            "once in any evaluation of a variant."
        ),
        "vcep_specifications": (
            "SpliceAI (PMID: 30661751): https://spliceailookup.broadinstitute.org/; "
            "REVEL (PMID: 27666373)."
        ),
        "vcep_strength_rules": {
            "supporting": (
                "For missense variants: REVEL score >=0.644 or SpliceAI score >=0.2. "
                "For synonymous and intronic variants: SpliceAI score >=0.2. "
                "(Modification Type: Disease-specific)"
            ),
        },
    },

    "PP4_MODERATE": {
        "criterion": "PP4_Moderate",
        "acmg_category": "Pathogenic",
        "strength_levels_defined": ["moderate"],
        "acmg_summary": (
            "Patient's phenotype or family history is highly specific for a disease with a single "
            "genetic etiology."
        ),
        "vcep_specifications": (
            "PP4_Moderate cannot be applied to variants that meet BS1_Supporting/BS1/BA1 criteria. "
            "If PP4_Moderate can be applied to a patient, they cannot be included in proband counting (PS4). "
            "See HHT phenotype document in attachments for information regarding Curacao phenotype requirements."
        ),
        "vcep_strength_rules": {
            "moderate": (
                "Patient's phenotype meets consensus clinical diagnostic (Curaçao) criteria for HHT, "
                "and sequencing and large deletion/duplication analysis was performed for both ENG and "
                "ACVRL1 with any other identified variants ruled out. "
                "(Modification Type: Disease-specific, Strength)"
            ),
        },
    },

    # ──────────────────────────────────────────────────────────────────────────
    # BENIGN CRITERIA — ACTIVE
    # ──────────────────────────────────────────────────────────────────────────

    "BA1": {
        "criterion": "BA1",
        "acmg_category": "Benign",
        "strength_levels_defined": ["stand_alone"],
        "acmg_summary": (
            "Allele frequency is above 5% in Exome Sequencing Project, 1000 Genomes or Exome "
            "Aggregation Consortium."
        ),
        "vcep_specifications": None,
        "vcep_strength_rules": {
            "stand_alone": (
                "Allele frequency is >=1% in general population databases (e.g. gnomAD) based on Popmax FAF. "
                "(Modification Type: Disease-specific)"
            ),
        },
    },

    "BS1": {
        "criterion": "BS1",
        "acmg_category": "Benign",
        "strength_levels_defined": ["strong", "supporting"],
        "acmg_summary": "Allele frequency is greater than expected for disorder.",
        "vcep_specifications": (
            "HHT is not known to be enriched in bottlenecked populations (e.g. Ashkenazi Jewish); "
            "therefore, Popmax FAF can be calculated and applied for bottlenecked populations for "
            "BS1 and BS1_Supporting criteria."
        ),
        "vcep_strength_rules": {
            "strong": (
                ">0.2% to <1% in general population databases (e.g. gnomAD) based on Popmax FAF, "
                "or if variant meets BS1_Supporting and has >=2 homozygotes. "
                "(Modification Type: Disease-specific, Strength)"
            ),
            "supporting": (
                ">0.08% to 0.2% (based on gnomAD Popmax FAF). "
                "(Modification Type: Disease-specific, Strength)"
            ),
        },
    },

    "BS3": {
        "criterion": "BS3",
        "acmg_category": "Benign",
        "strength_levels_defined": ["supporting"],
        "acmg_summary": (
            "Well-established in vitro or in vivo functional studies show no damaging effect on "
            "protein function or splicing."
        ),
        "vcep_specifications": (
            "Normal protein expression cannot be used as benign evidence because protein function "
            "can still be altered (e.g. pathogenic dominant negative variants)."
        ),
        "vcep_strength_rules": {
            "supporting": (
                "mRNA splicing assays; "
                "Intracellular signaling assays: BRE/CAGA-luciferase, Gal4 Smad1/Smad3 for "
                "TGF-beta/BMP9 signaling; "
                "Binding assays: BMP9 binding, transcription factor Sp1, BMP9 protein-protein "
                "interaction (BLI); "
                "Subcellular protein localization; "
                "Morphology: Morphology & actin cytoskeleton, tubulogenesis. "
                "(Modification Type: Disease-specific, Strength)"
            ),
        },
    },

    "BS4": {
        "criterion": "BS4",
        "acmg_category": "Benign",
        "strength_levels_defined": ["strong"],
        "acmg_summary": "Lack of segregation in affected members of a family.",
        "acmg_caveat": (
            "The presence of phenocopies for common phenotypes (i.e. cancer, epilepsy) can mimic "
            "lack of segregation among affected individuals. Also, families may have more than one "
            "pathogenic variant contributing to an autosomal dominant disorder, further confounding "
            "an apparent lack of segregation."
        ),
        "vcep_specifications": (
            "See HHT phenotype document in attachments for assignment of affected/unaffected status "
            "for purpose of inclusion in cosegregation study."
        ),
        "vcep_strength_rules": {
            "strong": (
                "Lack of segregation in affected members of a family. "
                "(Modification Type: Clarification, Disease-specific)"
            ),
        },
    },

    "BP2": {
        "criterion": "BP2",
        "acmg_category": "Benign",
        "strength_levels_defined": ["supporting"],
        "acmg_summary": (
            "Observed in trans with a pathogenic variant for a fully penetrant dominant gene/disorder "
            "or observed in cis with a pathogenic variant in any inheritance pattern."
        ),
        "vcep_specifications": "Variants must be confirmed in trans.",
        "vcep_strength_rules": {
            "supporting": (
                "Observed in trans with a pathogenic or likely pathogenic variant based on HHT VCEP rules. "
                "(Modification Type: Disease-specific)"
            ),
        },
    },

    "BP4": {
        "criterion": "BP4",
        "acmg_category": "Benign",
        "strength_levels_defined": ["supporting"],
        "acmg_summary": (
            "Multiple lines of computational evidence suggest no impact on gene or gene product "
            "(conservation, evolutionary, splicing impact, etc.)."
        ),
        "acmg_caveat": (
            "As many in silico algorithms use the same or very similar input for their predictions, "
            "each algorithm cannot be counted as an independent criterion. BP4 can be used only once "
            "in any evaluation of a variant."
        ),
        "vcep_specifications": (
            "SpliceAI (PMID: 30661751): https://spliceailookup.broadinstitute.org/; "
            "REVEL (PMID: 27666373)."
        ),
        "vcep_strength_rules": {
            "supporting": (
                "For missense variants: REVEL score <=0.15 and SpliceAI score <=0.1. "
                "For synonymous and intronic variants: SpliceAI score <=0.1. "
                "(Modification Type: Disease-specific)"
            ),
        },
    },

    "BP5": {
        "criterion": "BP5",
        "acmg_category": "Benign",
        "strength_levels_defined": ["supporting"],
        "acmg_summary": "Variant found in a case with an alternate molecular basis for disease.",
        "vcep_specifications": None,
        "vcep_strength_rules": {
            "supporting": (
                "Apply if a likely pathogenic or pathogenic variant (based on HHT VCEP rules) is found in ENG. "
                "(Modification Type: Disease-specific)"
            ),
        },
    },

    "BP7": {
        "criterion": "BP7",
        "acmg_category": "Benign",
        "strength_levels_defined": ["supporting"],
        "acmg_summary": (
            "A synonymous variant for which splicing prediction algorithms predict no impact to the "
            "splice consensus sequence nor the creation of a new splice site AND the nucleotide is "
            "not highly conserved."
        ),
        "vcep_specifications": (
            "For synonymous and intronic variants: SpliceAI score <=0.1. "
            "Note: If no causative variant is found in ENG or ACVRL1, and the patient's clinical "
            "presentation and/or family history is highly suspicious for HHT, be careful to not "
            "dismiss intronic variants or synonymous variants in the last nucleotide of the exon "
            "based on computational predictions. "
            "Example 1: ENG c.219G>A; p.Thr73= is not predicted to significantly alter splicing "
            "(SpliceAI: 0.02) and the nucleotide is weakly conserved; however, this variant was "
            "later shown to cause exon skipping (PMID: 17384219). "
            "Example 2: SpliceAI does not predict splicing effects for some deep intronic ACVRL1 "
            "intron 9 CT-rich hotspot variants (PMID: 30244195). Therefore, variants that create a "
            "new 'AG' cryptic splice site in this region should not be ruled out based on SpliceAI "
            "prediction alone."
        ),
        "vcep_strength_rules": {
            "supporting": (
                "A synonymous or intronic variant for which SpliceAI predicts no impact to the splice "
                "consensus sequence nor the creation of a new splice site. Can be used together with "
                "BP4 evidence. "
                "(Modification Type: Disease-specific)"
            ),
        },
    },
}


# ──────────────────────────────────────────────────────────────────────────────
# RULES FOR COMBINING CRITERIA (PDF page 7)
# ──────────────────────────────────────────────────────────────────────────────

COMBINING_RULES = {
    "pathogenic": [
        "1 Very Strong (PVS1) AND >=1 Strong (PVS1_Strong, PS1, PS2, PS3, PS4, PM5_Strong, PP1_Strong)",
        "1 Very Strong (PVS1) AND >=2 Moderate (PVS1_Moderate, PS3_Moderate, PS4_Moderate, PM1, PM4, PM5, PP1_Moderate, PP4_Moderate)",
        "1 Very Strong (PVS1) AND 1 Moderate AND 1 Supporting (PS3_Supporting, PS4_Supporting, PM2_Supporting, PP1, PP3)",
        "1 Very Strong (PVS1) AND >=2 Supporting",
        ">=2 Strong",
        "1 Strong AND >=3 Moderate",
        "1 Strong AND 2 Moderate AND >=2 Supporting",
        "1 Strong AND 1 Moderate AND >=4 Supporting",
    ],
    "likely_pathogenic": [
        "1 Very Strong (PVS1) AND 1 Moderate",
        "1 Strong AND 1 Moderate",
        "1 Strong AND >=2 Supporting",
        ">=3 Moderate",
        "2 Moderate AND >=2 Supporting",
        "1 Moderate AND >=4 Supporting",
        "1 Strong AND 2 Moderate",
        "1 Very Strong (PVS1) AND 1 Supporting (PM2_Supporting)",
    ],
    "benign": [
        ">=2 Strong (BS1, BS4)",
        "1 Stand Alone (BA1)",
    ],
    "likely_benign": [
        ">=2 Supporting (BS1_Supporting, BS3_Supporting, BP2, BP4, BP5, BP7)",
        "1 Strong (BS1)",
        "1 Strong (BS1, BS4) AND 1 Supporting",
    ],
}


# ──────────────────────────────────────────────────────────────────────────────
# NOT APPLICABLE — per HHT VCEP CSpec GN135 v1.1.0
# ──────────────────────────────────────────────────────────────────────────────

NOT_APPLICABLE = {
    "PS2": "De novo variants are rare in HHT (see HHT phenotype document; low-level mosaicism in parents has been observed: PMIDs 29736967, 21651515, 21378382, 21415079).",
    "PM3": "HHT is autosomal dominant disorder.",
    "PM6": "De novo variants are rare in HHT. De novo variants should be confirmed not presumed for HHT.",
    "PP2": "Does not apply to ACVRL1 (Z-score 2.45).",
    "PP5": "This criterion is not for use as recommended by the ClinGen Sequence Variant Interpretation VCEP Review Committee. PubMed: 29543229.",
    "BS2": "Full penetrance at an early age is not observed in HHT.",
    "BP1": "Missense variants commonly seen in HHT genes.",
    "BP3": "Not Applicable.",
    "BP6": "This criterion is not for use as recommended by the ClinGen Sequence Variant Interpretation VCEP Review Committee. PubMed: 29543229.",
}


# ──────────────────────────────────────────────────────────────────────────────
# Query helpers
# ──────────────────────────────────────────────────────────────────────────────

def query(criterion: str) -> dict | None:
    """Retrieve the PlanRAG entry for a given ACMG criterion."""
    key = criterion.upper().replace("-", "_").replace(" ", "_")

    if key in PLANRAG_DB:
        return PLANRAG_DB[key]

    for db_key, entry in PLANRAG_DB.items():
        if entry["criterion"].upper().replace("_", "").replace(" ", "") == key.replace("_", "").replace(" ", ""):
            return entry

    if key in NOT_APPLICABLE:
        return {
            "criterion": criterion,
            "not_applicable": True,
            "reason": NOT_APPLICABLE[key],
        }

    return None


def get_all_active_criteria() -> list[str]:
    return list(PLANRAG_DB.keys())


def get_not_applicable_criteria() -> list[str]:
    return list(NOT_APPLICABLE.keys())