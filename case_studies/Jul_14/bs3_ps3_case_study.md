## BS3/PS3 Root Cause Reassessment: Previous Diagnosis vs. Actual Issue

Yesterday, the initial investigation suggested that the five failed variants did not have available rsIDs. Since the current workflow relies on **LitVar2** to retrieve publication identifiers (PMIDs), the hypothesis was that missing rsIDs prevented LitVar2 from finding relevant papers. Based on this assumption, the proposed solution was to implement additional fallback strategies to query PMIDs from alternative sources.

---

## New Finding: The Failure Was Caused by an API Calling Bug

After further debugging today, I discovered that the previous conclusion was incorrect. The failure was **not caused by the absence of rsIDs**. Instead, the problem was caused by a bug in passing rsids to downstream functions

After fixing the bug, I reran the functional evidence retrieval workflow. The updated results show that LitVar2 can successfully retrieve publications for some variants, while other failures are caused by LitVar2 genuinely returning no available papers or Litvar 2 failure

---

## Updated Functional Evidence Retrieval Results

| Variant | LitVar2 Retrieval Result | Explanation |
| --- | --- | --- |
| Variant 0 | ✅ LitVar2 returned PMID(s) | The PMID(s) were incorrectly filtered out during the abstract screening phase |
| Variant 1 | ⚠️ LitVar2 API error | The LitVar2 request failed due to an API calling error |
| Variant 2 | ℹ️ LitVar2 returned no paper | No publication was found by LitVar2 for this variant |
| Variant 3 | ℹ️ LitVar2 returned no paper | No publication was found by LitVar2 for this variant |
| Variant 4 | ✅ LitVar2 returned PMID(s) | The PMID(s) were incorrectly filtered out during the abstract screening phase |

---

## Fixing False Negative Cases: Incorrect Filtering During Abstract Screening

After fixing the LitVar2 retrieval issue, I found that some variants (e.g., Variant 0 and Variant 4) were not failing because relevant publications were missing. Instead, the publications were successfully retrieved, but they were incorrectly removed during the **LLM filtering stage**.

To understand this issue, it is important to first review the workflow of the `functional_evidence` tool:

```
1. VEP Annotation
    ↓
    Query Ensembl VEP for: rsID, HGVSc, HGVSp, gene symbol

2. LitVar2 Query
    ↓
    Search LitVar2 for papers mentioning the variant

3. PubMed Retrieval
    ↓
    Fetch paper metadata (title, abstract) from PubMed

4. LLM Filtering
    ↓
    Use LLM to identify papers containing functional experiments

5. Experiment Extraction
    ↓
    Extract detailed experiment information using LLM
    (Standard or Agentic extraction mode)
```

---

## Root Cause: LLM Incorrectly Filtered Relevant Papers

The issue occurred at **Step 4: LLM Filtering**.

The purpose of this step is to perform a high-sensitivity screening of retrieved papers and determine whether the abstract contains evidence of functional experiments. The system prompt explicitly instructs the LLM to:

- Remain highly sensitive and avoid missing potential functional evidence.
- Consider papers containing evidence of functional assays even when information is incomplete.

However, after analyzing the failed cases, I found an ambiguity in the prompt design.

On one hand, the prompt instructed the LLM to identify **any traces of functional experiments regardless of the variant**. On the other hand, it also instructed the LLM to focus on the **specific variant currently being investigated**.

These two requirements introduced confusion:

- The LLM needed to determine whether a paper contained functional evidence.
- At the same time, it needed to decide whether it should retain all functional evidence or only functional evidence related to a parciular variant.

In some cases, the LLM became overly strict and filtered out papers because the abstract did not explicitly mention the exact target variant, even though the paper contained relevant functional experiments that should have been reviewed during downstream extraction.

---

## ✅ Prompt Improvement

To address this issue, I modified the LLM filtering prompt with two improvements:

### 1. Clarified the Screening Objective

The updated prompt provides clearer instructions that the screening stage should prioritize **sensitivity over specificity**.

The LLM should retain papers when there is reasonable evidence that they contain any relevant functional experiments, even if the abstract does not provide complete variant-level details.

The final determination of whether the experiment applies to the specific variant should be handled during the downstream experiment extraction stage.

### 2. Added Few-Shot Prompting

I also introduced **few-shot prompting**

These examples demonstrate:

- What types of abstracts should be considered positive.
- Why potentially relevant functional studies should not be filtered out prematurely.

The goal is to help the LLM better understand its role in the pipeline and make decisions more consistent with the intended high-sensitivity screening strategy.

---

## Remaining Limitation: Abstract-Only Screening Is Insufficient

Although the prompt improvements reduce false negatives during abstract screening, I identified another limitation in the current framework.

Currently, the functional evidence workflow only analyzes **paper abstracts**. However, abstracts often provide only a brief summary of the study and may omit important experimental details.

After reviewing failed examples, I found that many relevant papers had abstracts containing minimal information about:

- The tested variants
- The experimental system
- Functional assays performed
- The observed functional effects

As a result, the LLM cannot always make a reliable judgment based only on the abstract.

---

## Current Development: Adding PDF-Based Evidence Extraction

To address this limitation, I am currently implementing **full-text PDF extraction** into the functional evidence workflow.

The updated workflow will allow the system to:

1. Retrieve candidate publications through LitVar2.
2. Perform initial screening using abstracts.
3. Analyze full-text PDFs instead of only the abstract.
4. Extract detailed functional experiment information from the complete paper.

This should improve recall for functional evidence retrieval and reduce false negatives caused by insufficient information in abstracts.\

---

## 🚧 Current Blocker: Unstable PDF Processing with External URLs

Although adding full-text PDF extraction is the next step to improve functional evidence retrieval, the implementation is currently blocked by an issue with **feeding external PDF URLs directly to LLMs**.

Currently, we attempt to provide the LLM with links to publicly available PDF documents and let the model extract relevant functional evidence directly from the full text. However, this process has proven to be unstable.

The PDF extraction component is still under development, and I have not completed this improvement yet.

Once the PDF ingestion pipeline becomes stable, the next step will be to integrate it into the existing `functional_evidence` workflow and evaluate whether full-text analysis can recover additional functional evidence that was missed during abstract-only screening.
                        