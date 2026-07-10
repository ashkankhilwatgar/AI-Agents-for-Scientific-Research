## Case Study: Criterion-Level Reasoning Quality Behind Final-Label Mismatches (25-Variant HHT Batch)

### Motivation

`evaluation/question1.py` scores the pipeline at the per-criterion level — for every (variant, criterion) pair the system evaluated, did it correctly decide "applies" vs. "does not apply" against the gold `gt_criteria_applied` / `gt_criteria_not_met` labels? Run against a 25-variant batch (`outputs/batch_20260707_155149`, scored with `hht_script_2.csv`), the aggregate numbers were strong — accuracy 0.961, precision 1.000, recall 0.958, F1 0.979 across 51 scored criterion instances, with perfect scores on 9 of 11 distinct criteria. But aggregate numbers, whether at the criterion level or the final-classification level, still collapse each divergence into an undifferentiated "miss." Of the 25 final classifications in this batch, 4 diverged from the gold label. This case study traces each of those 4 down to the criterion level to check whether the divergence reflects a reasoning defect in the multi-agent framework or something else — and, in one case, a genuine framework reliability issue worth fixing.

All classification rules referenced below are drawn from the ClinGen HHT Variant Curation Expert Panel specifications (GN135 v1.1.0 for *ACVRL1*, GN136 v1.1.0 for *ENG*), as encoded in the pipeline's PlanRAG combining-rule tables.

---

### Case 1: `NM_001114753.3:c.1701del` — a third instance of the PS4 evidence-access gap (Pathogenic → Likely Pathogenic)

**Gold classification:** Pathogenic — gold criteria: `PVS1; PM2_Supporting; PS4_Supporting`
**Pipeline classification:** Likely Pathogenic — combining rule matched: *"PVS1 + 1 Supporting"*

- **PVS1 (applies, very_strong).** The variant is a frameshift in *ENG* at codon 567. The reasoning correctly cites the *ENG* PVS1 decision tree's NMD boundary (codon ≤ 594 → Very Strong) and applies it.
- **PM2_Supporting (applies, supporting).** Total allele count of 0 in gnomAD — correctly identified as absent.
- **PS4 (does not apply).** The pipeline queried ClinVar's HHT VCEP SCV, ERepo, and LOVD (all returned nothing), then searched PubMed, which returned 468 articles — but none of the top 10 retrieved contained a specific proband count or case report for this exact variant, so the reasoning correctly concludes 0 confirmed probands and withholds PS4 rather than guessing from a broad, unconfirmed literature hit count.

Given PVS1 (very strong) + PM2_Supporting (supporting), the combining-rule engine correctly returns *"PVS1 + 1 Supporting → Likely Pathogenic."* Reaching Pathogenic requires *"PVS1 + ≥2 Supporting"* — one supporting-level criterion short, exactly as in the PVS1/PS4 pattern already documented for `c.1217G>A` and `c.620del` in the companion case study. This is now a third independent example of the same failure mode: the HHT VCEP curators' PS4_Supporting call rests on proband evidence not discoverable through the four public sources (ClinVar VCEP SCV comments, ERepo, LOVD, PubMed metadata) this pipeline can query — not a defect in how the pipeline reasons about the evidence it retrieves.

---

### Case 2: `NM_000020.3:c.293A>G` — a functional-evidence (PS3) retrieval gap, not previously documented (Likely Pathogenic → VUS)

**Gold classification:** Likely Pathogenic — gold criteria: `PM2_Supporting; PS3_Supporting; PS4`
**Pipeline classification:** Variant of Uncertain Significance — combining rule: *"No combining criteria rule was satisfied"*

- **PM2_Supporting (applies, supporting).** Absent from gnomAD — correctly identified.
- **PS4 (applies, strong).** The ClinVar HHT VCEP SCV submission reports 5 probands with an HHT phenotype (citing PMIDs 16690726 and 18498373); the reasoning correctly applies the HHT VCEP's proband-count mapping (≥4 probands → PS4_Strong).
- **PS3 (does not apply).** The `functional_evidence` tool returned no experiments for this variant, and the reasoning correctly applies the documented shortcut ("no functional experiments retrieved → PS3 does not apply") rather than fabricating evidence.

This is a new instance of the evidence-access-gap pattern, but on a different criterion and a different tool than previously documented: the gold PS3_Supporting call implies the HHT VCEP curators had access to a functional study for this variant that the pipeline's functional-evidence search did not surface. With only PM2_Supporting + PS4_Strong captured, the bucket counts (`sup=1, s=1`) do not satisfy any Likely Pathogenic rule in the combining table (the applicable rule requires 1 Strong + ≥2 Supporting, or comparable combinations — 1 Strong + 1 Supporting alone is not a defined LP rule in this VCEP's table), so the system correctly falls through to VUS given the evidence it has. The shortfall is one missing supporting-level criterion, traceable to a functional-evidence literature/database coverage gap rather than to the reasoning or arithmetic — the same class of issue as the two cases above, but flagging `PS3`/`functional_evidence` as a second tool worth prioritizing for improved coverage alongside PS4's proband search.

---

### Case 3: `NM_000020.3:c.1348A>G` — a stricter, VCEP-rule-literal call on the benign side (Likely Benign → VUS), plus a distinct technical failure worth separating out

**Gold classification:** Likely Benign — gold criteria: `BS1` (no other criteria listed as applied)
**Pipeline classification:** Variant of Uncertain Significance — combining rule: *"No combining criteria rule was satisfied"*

- **BS1 (applies, benign_supporting).** gnomAD popmax FAF of 0.001739 in the 'mid' population. The reasoning correctly walks the tiered FAF/homozygote-count decision steps (BA1 no; BS1_Strong homozygote route no, since only 1 homozygote; BS1_Strong FAF route no; falls into the BS1_Supporting band of 0.0008–0.002) — this criterion call **matches gold exactly**, both in outcome and strength.

The final-label mismatch here is not a reasoning error on any evaluated criterion — it is a direct, checkable consequence of the HHT VCEP combining-rule table itself. That table's Likely Benign rules are `{bs:1, bsup:1}`, `{bs:1}` alone, or `{bsup:2}` (`data/planrag.py`, lines 1142–1146). A single `BS1_Supporting` with no other benign criterion satisfies none of these three rules, so the pipeline's own rule table dictates VUS given exactly the evidence gold agrees applies. ClinVar's Likely Benign call for this variant rests on either an implicit additional consideration outside the codified rule table or a more lenient practical threshold than the VCEP's formal combining-rule specification allows for — the same class of principled, rule-literal conservatism already documented for the PM5 case in the companion case study, here appearing on the benign side of the table.

**One caveat, reported transparently rather than folded into the narrative above:** this variant's `PM2_SUPPORTING` criterion did not complete — it failed with `"Judge agent exceeded retry limit (5) without resolving reasoning error"`, a genuine framework reliability issue (the Judge agent repeatedly rejected the Task agent's reasoning without converging) rather than an evidence gap or a defensible rule-literal decision. In this specific case the failure is very unlikely to have changed the final label — a variant with a gnomAD popmax FAF of 0.0017 (well above typical PM2 rarity thresholds) would almost certainly have been correctly scored as PM2-does-not-apply had the Judge agent resolved — so it does not undermine the BS1-driven analysis above. But it is a distinct, reproducible failure mode (see the companion investigation into `PM2_SUPPORTING`/`PS4` Judge retry-limit errors recurring across this batch) that should be fixed and tracked separately from the rule-literal VUS call, rather than being cited as supporting evidence for it.

---

### Synthesis

Three of the four final-label mismatches in this batch (`c.1701del`, `c.293A>G`, and the benign-rule-table reasoning in `c.1348A>G`) trace to causes external to the multi-agent framework's reasoning quality: two are upstream evidence-retrieval gaps (PS4 proband search, PS3 functional-evidence search) where the pipeline's per-criterion evidence citation, VCEP-specific threshold application, and combining-rule arithmetic were all correct given what it could retrieve; the third is a case where the pipeline's rule-table combining logic is demonstrably *more literal* than the gold label, not less correct. Only the Judge-agent retry-limit failure on `c.1348A>G`'s `PM2_SUPPORTING` check is a genuine system defect — and it is a reliability/robustness issue in agent-to-agent convergence, not a criterion-reasoning error, and did not change that variant's outcome in this instance. This reinforces the same conclusion as the companion case study: final-label accuracy conflates "the system is missing external data sources a human curator had access to" and "the system's combining-rule logic is doing exactly what the VCEP specification says" with actual reasoning failures, and per-criterion evaluation (via `evaluation/question1.py`) is what makes that distinction legible.
