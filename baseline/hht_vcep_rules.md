# HHT VCEP ACMG/AMP Classification Rules
*(ClinGen Hereditary Hemorrhagic Telangiectasia Variant Curation Expert Panel — CSpec GN135 v1.1.0 for ACVRL1, GN136 v1.1.0 for ENG)*

This document defines the criteria, thresholds, and combining rules used to classify a germline variant in *ACVRL1* or *ENG* as Pathogenic, Likely Pathogenic, VUS, Likely Benign, or Benign, per the HHT VCEP specification. Use this as the authoritative rule set. Do not substitute the standard/generic ACMG rules where they differ from what's written here — the HHT VCEP has modified several standard ACMG thresholds and excluded several standard criteria outright.

## How to use this document

For a given variant, evaluate every criterion below using only your own background knowledge — do not attempt to browse the web, call any tool, or look anything up. For any criterion whose evaluation requires a specific quantitative value you cannot be certain of from memory (e.g. an exact gnomAD allele count, an exact REVEL/SpliceAI score, an exact ClinVar proband count), state explicitly that the value is unknown to you rather than inventing a plausible-sounding number. Distinguish clearly between "I recall specific evidence for this variant" and "I am inferring from general knowledge of this gene/region" in your reasoning.

For each criterion, output: whether it applies (true/false/unknown), its strength (if variable-strength), and a short evidence/reasoning statement.

---

## Automatable criteria (13)

### PM2_Supporting (Pathogenic, Supporting)
Variant absent or at extremely low frequency in population databases.
**Threshold:** Absent from gnomAD entirely, OR total allele count (AC) < 6 across all gnomAD populations, OR allele frequency < 0.00004 (0.004%) in any single gnomAD subpopulation. (Not Popmax FAF — raw AC and subpopulation AF only.)

### BA1 (Benign, Stand-Alone)
Allele frequency high enough for stand-alone benign classification.
**Threshold:** Popmax FAF (filtering allele frequency) >= 0.01 (1%) in gnomAD.
If BA1 applies, the variant is Benign regardless of all other evidence, and PP4_Moderate cannot also apply.

### BS1 (Benign, Strong or Supporting — two tiers)
Allele frequency greater than expected for the disorder.
**Thresholds (Popmax FAF, including bottlenecked populations e.g. Ashkenazi Jewish):**
- BS1_Strong: Popmax FAF > 0.002 and < 0.01, OR (Popmax FAF in the BS1_Supporting range AND >= 2 homozygotes in gnomAD)
- BS1_Supporting: Popmax FAF > 0.0008 and <= 0.002
- Does not apply if BA1 already applies (BA1 supersedes).
- If BS1 or BS1_Supporting applies, PP4_Moderate cannot also apply.

### PS4 (Pathogenic, Strong / Moderate / Supporting — proband counting, not OR/RR)
Prevalence of the variant in affected individuals is significantly increased vs. controls, using proband counting rather than odds ratio/relative risk.
**Requires PM2_Supporting to also apply.** Phenotype must be consistent with HHT (Curaçao criteria). Probands counted toward PP4_Moderate cannot also count here (mutual exclusivity).
**Thresholds:** Strong = 4+ probands; Moderate = 2–3 probands; Supporting = 1 proband; 0 probands = does not apply.

### PM1 (Pathogenic, Moderate only) — gene-specific critical residues
Variant located in a critical residue. **Missense variants only.**
If PM1 applies, cannot combine with PM5_Strong (PM5_Moderate + PM1 is allowed).

- **ACVRL1 (NM_000020.3) critical regions:** glycine-rich loop (residues 209–216), phosphate anchor (residue 229), C-helix E/phosphate-anchor pairing (residue 242), catalytic loop (residues 329–335), metal-binding loop (residues 348–351), BMP10 interaction cluster (residues 40, 54, 56, 57, 58, 59, 66, 71, 72, 73, 75, 76, 78, 79, 80, 82, 83, 84, 85, 87).
- **ENG (NM_001114753.3) critical regions:** BMP9 binding sites (residues 278, 282), cysteine residues classified LP/P by HHT VCEP (residues 207, 363, 382, 412, 549), cysteine residues critical to function via disulfide bonds (residues 350, 394).

### PVS1 (Pathogenic, Very Strong / Strong / Moderate, or N/A) — null variant decision tree
Applies to frameshift, nonsense, canonical +/-1,2 splice site, initiation codon, or exon/gene deletion/duplication variants in ACVRL1 or ENG (both established loss-of-function/haploinsufficiency disease mechanisms).

- **ACVRL1** key boundaries: codon 442 = NMD boundary; codon 490 = critical-region boundary; protein length 503 aa.
- **ENG** key boundaries (estimated, lower confidence): codon 594 = NMD boundary; codon 580 = critical-region boundary; protein length 658 aa, 15 exons. ENG exon 13 frameshifts are predicted NMD per VCEP evidence.

General logic: nonsense/frameshift/splice variants predicted to trigger nonsense-mediated decay (premature termination codon at or before the NMD boundary codon) → PVS1 (Very Strong). If not NMD-predicted, but the truncated/altered region is critical to protein function (at or before the critical-region boundary codon) → PVS1_Strong. If the region's role is unknown and the variant removes <10% of the protein → PVS1_Moderate. Full gene deletions → PVS1. Initiation codon variants with no known alternative start codon → PVS1_Moderate.

### PM5 (Pathogenic, Strong or Moderate) — novel missense at a residue with an established different LP/P missense
**Missense variants only.** Requires a *different* amino acid substitution at the *same codon* previously classified LP/P per HHT VCEP rules (not just any ClinVar submission — must be VCEP-classified).
**Thresholds:** >=2 different LP/P missense at the same codon → Strong; exactly 1 → Moderate.
Cannot combine PM5_Strong with PM1 (auto-downgrade PM5 to Moderate if both would otherwise apply — this incompatibility rule must be applied before final scoring).

### PS3 (Pathogenic, Strong only) — functional evidence of damage
Well-established functional studies (mRNA splicing assay, or >=2 different concordant non-splicing assay types — e.g. BMP9/TGF-beta signaling, binding, subcellular localization/trafficking, or morphology/tubulogenesis assays) showing a damaging effect. Normal protein expression/abundance alone is not sufficient evidence either way. Ambiguous or conflicting results do not count.

### PS1 (Pathogenic, Strong only) — same amino acid change as an established pathogenic variant
**Missense variants only.** Requires the exact same amino acid change (any nucleotide change) as a variant already classified Pathogenic/Likely Pathogenic by HHT VCEP or 2+ star ClinVar consensus. Does not apply if the variant in question likely affects splicing rather than acting purely at the protein level.

### PP3 (Pathogenic, Supporting only) — computational evidence of damage
**Thresholds:** Missense — REVEL >= 0.644 OR SpliceAI (any delta score) >= 0.2. Synonymous/intronic — SpliceAI >= 0.2. Can be used only once per variant. Redundant/blocked if PVS1 already applies.

### PM4 (Pathogenic, Moderate only) — protein length change
In-frame insertion/deletion in a non-repeat region, or a stop-loss variant.

### BP4 (Benign, Supporting only) — computational evidence of no damage
**Thresholds:** Missense — REVEL <= 0.15 AND SpliceAI (all delta scores) <= 0.1 (both required). Synonymous/intronic — SpliceAI <= 0.1. Redundant/blocked if PVS1 already applies.

### BP7 (Benign, Supporting only) — synonymous/intronic variant with no predicted splice impact
**Thresholds:** Synonymous or intronic variant AND all four SpliceAI delta scores <= 0.1. Caution: do not dismiss deep intronic or last-exon-nucleotide synonymous variants based on SpliceAI alone if clinical suspicion is high — some validated splice variants have low SpliceAI scores (e.g. ENG c.219G>A, ACVRL1 intron 9 CT-rich hotspot).

---

## Manual-input criteria (5) — require patient-specific data not derivable from the variant alone

These cannot be meaningfully evaluated from the variant identity alone; they require real patient/family data. Mark as "not evaluable — no patient data provided" rather than guessing, unless synthetic/example patient data is explicitly supplied to you alongside the variant.

- **PP1** (Supporting/Moderate/Strong) — co-segregation with disease across affected family members. Meiosis-based: 3 meioses = Supporting, 4 = Moderate, 5+ = Strong.
- **BS4** (Strong only) — lack of segregation in affected family members. Caveat: phenocopies or a second pathogenic variant in the family can mimic lack of segregation.
- **BP2** (Supporting only) — confirmed in trans with a P/LP variant (per HHT VCEP rules); phase must be confirmed.
- **PP4_Moderate** (Moderate only) — patient meets Curaçao clinical criteria (>=3 of: spontaneous recurrent epistaxis, characteristic telangiectases, visceral lesions, affected first-degree relative) AND comprehensive ENG + ACVRL1 sequencing/deletion-duplication analysis ruled out other variants. Blocked if BA1/BS1/BS1_Supporting applies. Probands counted here cannot also count toward PS4.
- **BP5** (Supporting only, gene-specific) — patient also carries a P/LP variant (per HHT VCEP rules) in the *other* HHT gene (ACVRL1 variant → check for P/LP ENG variant, or vice versa).

---

## Criteria explicitly excluded / Not Applicable for HHT (do not apply these, regardless of evidence)

- **PS2** — de novo variants are rare in HHT; would need confirmation, not presumption; low-level parental mosaicism observed.
- **PM3** — HHT is autosomal dominant; the recessive trans mechanism this criterion assumes isn't relevant.
- **PM6** — same de novo rarity/confirmation issue as PS2.
- **PP5** — excluded per ClinGen SVI VCEP Review Committee recommendation (PMID 29543229).
- **BS2** — full penetrance at an early age is not observed in HHT, so this criterion's premise doesn't hold.
- **BP1** — missense variants are commonly disease-causing in HHT genes, so this criterion's premise (missense = usually benign) doesn't hold.
- **BP3** — excluded per HHT VCEP.
- **BP6** — excluded per ClinGen SVI VCEP Review Committee recommendation (PMID 29543229).

---

## Combining rules (final classification)

Map each applied criterion to a strength bucket: very_strong (vs), strong (s), moderate (m), supporting (sup) for pathogenic evidence; benign_stand_alone (ba), benign_strong (bs), benign_supporting (bsup) for benign evidence.

**Fixed-strength criteria** (always the same bucket): PM2_Supporting → supporting; PP3 → supporting; PP4_Moderate → moderate; PM1 → moderate; PM4 → moderate; PS1 → strong; BA1 → benign_stand_alone; BS4 → benign_strong; BP2 → benign_supporting; BP4 → benign_supporting; BP5 → benign_supporting; BP7 → benign_supporting.

**Variable-strength criteria** (bucket depends on the strength determined during evaluation): PVS1, PS3, PS4, PM5, PP1 (pathogenic side — very_strong/strong/moderate/supporting); BS1 (benign side — benign_strong/benign_supporting).

**Incompatibility rule (apply before final scoring):** if both PM1 and PM5 apply and PM5's strength would be "strong," downgrade PM5 to "moderate" before bucketing.

**Check rules in this order — first match wins:**

1. **Benign** if: BA1 applies alone, OR >= 2 Strong benign criteria apply.
2. **Likely Benign** if: (1 Strong benign + 1 Supporting benign), OR 1 Strong benign alone, OR >= 2 Supporting benign.
3. **Pathogenic** if any of: PVS1 + >=1 Strong; PVS1 + >=2 Moderate; PVS1 + 1 Moderate + 1 Supporting; PVS1 + >=2 Supporting; >=2 Strong; 1 Strong + >=3 Moderate; 1 Strong + 2 Moderate + >=2 Supporting; 1 Strong + 1 Moderate + >=4 Supporting.
4. **Likely Pathogenic** if any of: PVS1 + 1 Moderate; PVS1 + 1 Supporting; 1 Strong + 2 Moderate; 1 Strong + 1 Moderate; 1 Strong + >=2 Supporting; >=3 Moderate; 2 Moderate + >=2 Supporting; 1 Moderate + >=4 Supporting.
5. Otherwise: **VUS** (Variant of Uncertain Significance).

State clearly which rule matched, alongside the final classification, for transparency.
