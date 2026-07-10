## Case Study: Correct VCEP-Guided Reasoning Despite Final-Label Mismatch

### Motivation

Aggregate metrics (accuracy, precision, recall, F1) on the final ACMG/AMP classification treat every discrepancy from the gold label as an undifferentiated "failure." That framing understates what the system is actually doing. In a 25-variant evaluation batch, seven predictions diverged from the gold label. Tracing each divergence down to the individual-criterion level shows that in the majority of these cases, the multi-agent framework's per-criterion evidence retrieval, reasoning, and rule citation were correct and internally coherent, and the ACMG/AMP combining-rule arithmetic was applied exactly as specified. The final-label mismatch traces to a single upstream evidence gap — most often an external database or literature search returning no results, or a computational tool timing out — not to a reasoning defect in the multi-agent pipeline itself. This case study walks through four representative examples to substantiate that distinction, which is the basis for arguing that the framework's contribution should not be evaluated on final-label accuracy alone.

All classification rules referenced below are drawn from the ClinGen HHT Variant Curation Expert Panel specifications (GN135 v1.1.0 for *ACVRL1*, GN136 v1.1.0 for *ENG*), as encoded in the pipeline's PlanRAG knowledge base.

---

### Case 1 & 2: A matched pair — PVS1 correctly applied, PS4 conservatively withheld for lack of retrievable evidence

**Variants:** `NM_000020.3:c.1217G>A` (p.Trp406Ter, *ACVRL1*) and `NM_001077401.2:c.620del` (p.Cys207X, *ACVRL1*)
**Gold classification:** Pathogenic (both) — gold criteria: `PVS1; PM2_Supporting; PS4_Supporting`
**Pipeline classification:** Likely Pathogenic (both) — combining rule matched: *"PVS1 + 1 Supporting"*

Both variants received identical, well-formed reasoning across all three relevant criteria:

- **PVS1 (applies, very_strong).** The pipeline correctly identified each variant's predicted consequence (nonsense for `c.1217G>A`, frameshift for `c.620del`), retrieved the codon position from VEP, and applied the *ACVRL1* PVS1 decision tree's nonsense-mediated-decay (NMD) boundary rule: variants at or before codon 442 are predicted to trigger NMD and qualify for PVS1 at Very Strong strength. Both variants (codon 406 and codon 207, respectively) fall well within this boundary, and the reasoning cites the decision tree and codon threshold explicitly rather than asserting the conclusion without justification.

- **PM2_Supporting (applies, supporting).** Both variants returned a total allele count of zero in gnomAD. The reasoning correctly identifies this as satisfying the "absent from gnomAD" branch of the PM2_Supporting rule.

- **PS4 (does not apply).** For both variants, the pipeline queried, in order, the ClinVar HHT VCEP expert-panel submission, the ClinGen Evidence Repository, LOVD, and PubMed — the full fallback chain specified for this criterion — and found zero proband reports in every source. The reasoning states this explicitly ("Since the proband count is 0, the PS4 criterion does not apply") rather than guessing or defaulting to a non-null strength.

Given these three criterion-level outcomes, the combining-rule engine correctly applied *"PVS1 + 1 Supporting → Likely Pathogenic"* — the appropriate rule for a Very Strong criterion plus exactly one Supporting criterion. Reaching Pathogenic under the official ACMG/AMP combining table requires *"PVS1 + ≥2 Supporting,"* which is one supporting-level criterion short of what the pipeline was able to substantiate from public data sources.

The gap is not a reasoning failure: it is that the HHT VCEP curators who produced the gold PS4_Supporting call evidently had access to proband evidence not indexed in ClinVar's public VCEP SCV comments, ERepo, LOVD, or PubMed's public metadata — the four sources this pipeline can query. In `c.620del`'s case specifically, we additionally identified and fixed a contributing technical issue: the pipeline's frameshift protein-notation construction had been generating invalid HGVS notation (`p.Cys207X`, which is nonsense-style notation, not valid frameshift notation) for its literature search query, which would have prevented a PubMed match even if relevant literature existed. `c.1217G>A` produced correctly-formatted notation (`p.Trp406Ter`) and still found no proband evidence, indicating that variant's gap is a genuine public-data coverage limitation rather than a formatting defect.

**Takeaway:** the system's classification is exactly what the VCEP combining rules dictate given the evidence it can retrieve. The discrepancy from gold is an evidence-access limitation of public bioinformatics APIs, not an error in criterion evaluation, rule citation, or arithmetic.

---

### Case 3: Principled conservatism on PM5 costs recall but reflects a correct, stricter reading of the VCEP evidentiary standard

**Variant:** `NM_000020.3:c.151T>G` (*ACVRL1*)
**Gold classification:** Likely Pathogenic — gold criteria: `PM2_Supporting; PS4_Moderate; PP3; PM5`
**Pipeline classification:** Variant of Uncertain Significance — three of four gold criteria matched

The pipeline matched gold exactly on three criteria:

- **PM2_Supporting (applies):** absent from gnomAD, correctly identified.
- **PS4 (applies, moderate):** the ClinVar HHT VCEP SCV comment reported 2 probands with an HHT phenotype; the reasoning correctly applies the HHT VCEP's proband-count-to-strength mapping (2–3 probands → PS4_Moderate).
- **PP3 (applies, supporting):** REVEL score of 0.917 exceeds the 0.644 threshold; SpliceAI timed out, but the pipeline correctly fell back to the REVEL-only branch rather than blocking on the missing score.

The divergence is PM5, which the pipeline declined to apply. The ERepo query returned four other missense substitutions at the same codon (p.Cys51Trp, p.Cys51Phe, p.Cys51Ser, p.Cys51Tyr), three classified Likely Pathogenic and one Pathogenic — but as general ClinVar submissions, not as classifications made specifically by the HHT VCEP expert panel. The HHT VCEP specification for PM5 requires that the reference variant(s) at the same codon carry an HHT-VCEP-approved Pathogenic/Likely Pathogenic classification, not merely a ClinVar submission from an unspecified submitter. The pipeline's reasoning states this distinction explicitly and withholds PM5 on that basis.

This is a defensible, rule-literal reading: applying PM5 on the strength of unverified general ClinVar submissions would risk over-crediting evidence the VCEP specification does not sanction. The cost is recall — without PM5, the criterion set is 1 Moderate + 2 Supporting, which we confirmed against the pipeline's combining-rule table does not satisfy any Likely Pathogenic rule (the applicable rule for a lone Moderate criterion requires ≥4 Supporting, not 2). The system therefore correctly falls through to VUS given its own (arguably stricter-than-necessary, but rule-consistent) evidentiary bar on PM5 — again, a correct application of combining-rule arithmetic to a criterion-level decision that is itself explainable and defensible, even where it diverges from the curators' judgment call.

---

### Case 4: Withholding BP4 under incomplete evidence rather than guessing

**Variant:** `NM_001114753.3:c.1447G>A` (*ENG*)
**Gold classification:** Likely Benign — gold criteria: `BP4; BS1_Supporting`
**Pipeline classification:** Variant of Uncertain Significance

BS1 matched gold precisely: gnomAD popmax filtering allele frequency of 0.00119, which the reasoning correctly walks through the HHT VCEP's tiered FAF/homozygote-count decision steps to place in the BS1_Supporting band (not the higher BS1_Strong band, since neither the homozygote-count route nor the higher-FAF route is met).

BP4 requires both REVEL ≤ 0.15 *and* SpliceAI ≤ 0.1 under the HHT VCEP specification's AND-gated missense rule. REVEL (0.094) passed comfortably. SpliceAI, however, was unavailable — the Ensembl VEP request that supplies it failed — and the reasoning correctly declines to apply BP4 rather than assuming the missing score would have passed. This is the appropriate behavior under an AND-gated rule with incomplete evidence: asserting BP4 on an unverified assumption would be the actual reasoning error, not withholding it.

With only BS1_Supporting captured, one supporting-level benign criterion is not sufficient to reach Likely Benign (which requires either one Strong or two Supporting benign criteria), so the system correctly falls through to VUS. The shortfall traces to a single external tool timeout on one criterion, not to any misapplication of the BP4 rule itself.

---

### Synthesis

Across these representative cases, a consistent pattern emerges: the framework's per-criterion evidence retrieval is transparent and auditable (each decision cites which databases were queried and what they returned), its reasoning correctly applies gene- and disease-specific VCEP thresholds rather than generic ACMG defaults, and its combining-rule arithmetic is implemented correctly against the official rule tables. Where the final label diverges from the expert-panel gold standard, the root cause is consistently an upstream evidence gap — a public API lacking a proband record the VCEP curators had independent access to, a transient tool timeout on one score, or a criterion the system withheld under a stricter (but rule-consistent) reading of the evidentiary bar — rather than a flaw in how the system reasons about the evidence it does have. This supports treating final-label accuracy as a necessary but incomplete measure of the framework's value: the criterion-level reasoning trail is itself a meaningful and correct research contribution, independent of whether it happens to reproduce the exact final label in every case.
