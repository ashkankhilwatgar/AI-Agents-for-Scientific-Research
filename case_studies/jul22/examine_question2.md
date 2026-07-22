# Audit of `evaluation.question2`

Date: 2026-07-22

## Scope and inputs

This audit examines the current implementations of `evaluation/question2.py` and
`evaluation/question1.py`, the HHT scoring code, and these model outputs:

| Evaluation set | Gold file | Model output used | Batch state |
|---|---|---|---|
| 200 variants | `datasets/full_evaluation_dataset.csv` | `outputs/batch_20260708_132813/batch_summary.json` | 200/200 results, 200 successful |
| 48 annotated variants | `datasets/applied_only_evaluation_dataset.csv` | The matching 48 predictions filtered from `outputs/batch_20260708_132813/batch_summary.json` | 48/48 successful predictions |
| 25 variants | `datasets/hht_script_2.csv` | `outputs/batch_20260716_200245/batch_summary.json` | 25/25 result entries, 24 successful and 1 technical error |

I ask codex to check whether there is a 48 variant batch result in the outputs directory twice, and codex confirms that there is **no completed dedicated 48-target batch**. The newest dedicated run,
`outputs/batch_20260717_164439`, contains only 1 of 48 results. The 48-variant
statistics below therefore use the only complete coverage available: the same 48
variants extracted from the completed 200-variant run.

## Executive conclusion

The low strict final-class accuracies are real for the rows that were scored; they
are not caused by an incorrect `sklearn.metrics.accuracy_score` formula.

- 200 variants: 103 exact matches out of 200 = **51.50%**.
- 48 variants: 33 exact matches out of 48 = **68.75%**.
- 25 variants: 20 exact matches out of 24 successful predictions = **83.33%**.
  Counting the technical failure as incorrect gives an end-to-end accuracy of
  20/25 = **80.00%**.

**The primary reason that criterion level accuracy is high yet the overall accuracy**
**seems low is non-automatable criterions: sometimes our model is not bad at automatable**
**criterions; The non-automatable criterions is always the final factor required to**
**push a VUS to likely pathogenic.**

A strong validation result is that feeding the documented gold criterion **and
strength** sets into the current `tools.scoring.classify()` function reproduces:

## Reproduced Question 2 statistics

Precision, recall, and F1 below are unweighted macro averages across `B`, `LB`,
`VUS`, `LP`, and `P`.

| Set | Target N | Scored N | Correct | Technical failures | Accuracy | Macro precision | Macro recall | Macro F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 200 | 200 | 200 | 103 | 0 | 51.50% | 73.75% | 58.07% | 54.64% |
| 48 | 48 | 48 | 33 | 0 | 68.75% | 80.58% | 74.67% | 74.32% |
| 25, conditional on success | 25 | 24 | 20 | 1 | 83.33% | 93.33% | 87.43% | 88.32% |
| 25, end to end | 25 | 25 | 20 | 1 | 80.00% | Not currently computed | Not currently computed | Not currently computed |

The apparently high macro precision for the 200 set is not contradictory. For
example, the model predicted only seven `P` variants, and all seven were correct,
so `P` precision is 100%; however, it found only 7 of the 64 actual `P` variants,
so `P` recall is only 10.94%.

## Are the Question 2 statistics computed correctly?

### Yes

For the selected complete/matched inputs:

- label normalization produces exactly the same gold labels as
  `gt_classification_short` for all 200, 48, and 25 rows;
- normalized variant keys are unique in each gold file and batch;
- all intended predictions match the intended gold variants;
- the confusion matrices and the accuracy, macro precision, macro recall, and
  macro F1 calculations at `evaluation/question2.py:307-312` reproduce exactly;
- the 200 and complete-coverage 48 sets have no technical prediction failures.

Therefore, there is no arithmetic bug that artificially lowers 51.50% or 68.75%.

### Something question 2 eval script design we must be aware of 

#### 1. Technical errors are removed from the denominator — high severity

Rows with `pred_classification == "ERROR"` are dropped at
`evaluation/question2.py:191-195`. Metrics are then computed only on the remaining
rows.

For the 25 set this changes the headline from end-to-end 20/25 = 80.00% to
success-conditional 20/24 = 83.33%. Both numbers can be useful, but the report must
label them and show coverage.

#### 2. Extra predictions are labeled as failures 

Predictions with no gold match are dropped and added to `num_errors` at
`evaluation/question2.py:175-195`. Feeding the full 200 summary to the 48-row gold
file therefore reports 152 “failed variants,” even though those 152 predictions
succeeded and are merely out of scope. Therefore, when we runs the eval script, we
must make sure that the golden dataset contains all of predicted variants

## Why the 200-variant accuracy is 51.50%

### Error pattern

| Actual class | Support | Correct | Recall | Main errors |
|---|---:|---:|---:|---|
| B | 3 | 2 | 66.67% | 1 B -> VUS |
| LB | 58 | 35 | 60.34% | 23 LB -> VUS |
| VUS | 43 | 40 | 93.02% | 2 VUS -> LB; 1 VUS -> LP |
| LP | 32 | 19 | 59.38% | 13 LP -> VUS |
| P | 64 | 7 | 10.94% | 45 P -> LP; 12 P -> VUS |

The model predicts the middle classes far more often than the extremes:

- gold distribution: B=3, LB=58, VUS=43, LP=32, P=64;
- predicted distribution: B=2, LB=37, VUS=89, LP=65, P=7.

As we already discussed in the poster & the paper planning, the largest single 
pattern is 36 `P -> LP` cases where the pipeline found only
`PVS1 + PM2_Supporting`. Under the configured HHT rules, `PVS1 + 1 Supporting`
correctly yields **Likely Pathogenic**, not Pathogenic. The ClinVar gold `P` label
must therefore depend on additional evidence that the pipeline did not retrieve,
did not schedule, or that is absent from the local annotation.

### The full 200 set lacks criterion ground truth for most variants

Only 48/200 rows contain `gt_criteria_applied`; 152 rows have a final ClinVar label
but no positive criterion annotation in this dataset.

| Subset | Correct / N | Accuracy |
|---|---:|---:|
| 48 rows with applied-criterion annotations | 33/48 | 68.75% |
| 152 rows without applied-criterion annotations | 70/152 | 46.05% |

The unannotated subset contains 52 gold `P` variants, but only one was predicted
`P` (1.92% recall). It is not possible to determine the missing evidence for each
of those variants from the CSV because the criterion annotations are absent.

The strict accuracy also makes adjacent misses visible. Of the 97 errors, 84 are
only one class apart on `B < LB < VUS < LP < P`. Within-one-class agreement is
187/200 = 93.50%. This does **not** make 51.50% wrong; it shows that the dominant
failure is under/over-strength classification by one tier rather than arbitrary
class assignment.

## Why the 48-variant accuracy is 68.75%

The 48-row set is balanced enough to expose the criterion coverage problem:

- 155 gold-applied criterion-plus-strength items;
- 96 recovered with the exact criterion and exact strength (61.94%);
- 6 recovered at the right base criterion but wrong strength;
- 53 gold-applied items missing;
- 10 extra predicted-applied items not present in the gold applied set.

The 53 missing gold items are concentrated in:

| Criterion | Missing count | Main cause |
|---|---:|---|
| PP4 | 12 | omitted from the automated HHT schedule |
| PP1 | 9 | omitted/manual-deferred |
| PS3 | 8 | functional evidence retrieval commonly returned no experiments |
| BP5 | 8 | omitted/manual-deferred |
| BS3 | 5 | functional evidence retrieval returned no qualifying experiment |
| PS4 | 3 | evidence/agent/coverage errors |
| BP2 | 3 | omitted/manual-deferred |
| PP3 | 2 | evidence/criterion errors |
| PS1, PM5, BP4 | 1 each | evidence/filtering errors |

`pipeline.py:78` schedules only:

`PM2_SUPPORTING, PP3, BP4, BA1, BP7, BS1, PVS1, PM4, PM1, PS1, PM5, PS4, BS3, PS3`.

It omits PP4, PP1, BP5, and BP2 even though those criteria account for 32 of the
missing gold-positive items. Thirteen of the 15 final-class mismatches involve at
least one criterion that is not scheduled. Six involve a gold PS3 item that the
functional evidence step failed to recover.

All but two of the 15 errors are adjacent-class errors; within-one-class agreement
is 46/48 = 95.83%.

Also note that this result is calculated from the first version. Since we've tried to fix the 
false negative problem is PS3/PS3/PM5, these three criterion should have better performance
than what's shown in the statistics here.

## Complete list of 48-set final-class failures

Here “failure” means a final classification mismatch against gold. There are 15.
There are no whole-variant technical failures in this complete-coverage subset.

1. **`NM_000020.3:c.557G>T` — LP -> VUS.** Gold has
   `PP4_Moderate + PM2_Supporting + PS4_Moderate + PP3`. The pipeline correctly
   found PM2, PS4_Moderate, and PP3, but PP4 is not scheduled. The remaining
   1 Moderate + 2 Supporting items do not satisfy an LP rule; adding PP4_Moderate
   gives 2 Moderate + 2 Supporting and restores LP.

2. **`NM_000020.3:c.293A>G` — LP -> VUS.** Gold has
   `PM2_Supporting + PS3_Supporting + PS4_Strong`. The pipeline found PM2 and
   PS4_Strong, but functional evidence returned no experiments, so PS3 was false.
   Strong + 1 Supporting is insufficient; Strong + 2 Supporting gives LP.

3. **`NM_001114753.3:c.1145G>A` — P -> LP.** Gold includes
   PP4_Moderate, PM2_Supporting, PS3_Supporting, PS4_Strong, PM1, and PP1. The
   pipeline produced PM2, PM1, PS4_Strong, and an extra PM5_Moderate, yielding
   1 Strong + 2 Moderate + 1 Supporting. PS3 had no retrieved experiments; PP4
   and PP1 are unscheduled. The scorer correctly returns LP for the predicted
   buckets; the missing evidence is what prevents P.

4. **`NM_001114753.3:c.1319T>G` — LP -> VUS.** Gold has PP4_Moderate,
   PP1_Strong, PM2_Supporting, and PS4_Moderate. PP4 and PP1 are unscheduled, and
   PS4 failed with `Judge agent exceeded retry limit (5) without resolving
   reasoning error`. Only PM2_Supporting remained.

5. **`NM_001114753.3:c.1762G>A` — LB -> VUS.** Gold has BP5 + BP4.
   BP4 was correctly applied from REVEL 0.043 and SpliceAI 0, but BP5 is omitted
   from the automated HHT schedule. One benign Supporting item is VUS; two yield
   LB.

6. **`NM_001114753.3:c.1586G>A` — P -> VUS.** Gold has PP4_Moderate,
   PP1_Strong, PM2_Supporting, and PS4_Strong. The pipeline found only PM2 and
   PS4_Strong. PP4 and PP1 are unscheduled. Gold has two Strong criteria
   (PP1_Strong + PS4_Strong), which is Pathogenic; the prediction has only
   1 Strong + 1 Supporting, which is VUS.

7. **`NM_001114753.3:c.991G>A` — P -> VUS.** Gold has PP4_Moderate,
   PM2_Supporting, PS3_Strong, PS4_Strong, and PP1. The pipeline found PM2 and
   PS4_Strong. PS3 returned no experiments; PP4 and PP1 are unscheduled. The two
   gold Strong criteria would satisfy P, while the predicted set does not reach LP.

8. **`NM_001114753.3:c.662T>C` — LP -> VUS.** Gold has PP4_Moderate,
   PM2_Supporting, PS3_Supporting, and PS4_Strong. The pipeline found PM2 and
   PS4_Strong. PS3 returned no experiments and PP4 is unscheduled, leaving
   Strong + 1 Supporting instead of an LP combination.

9. **`NM_001114753.3:c.2T>G` — P -> LP.** Gold uses PVS1_Strong,
   PS4_Strong, PP4_Moderate, PM2_Supporting, and PM5_Strong. The pipeline assigned
   PVS1_Moderate to the start-loss variant, found PS4_Strong and PM2, filtered PM5
   out as missense-only, and did not schedule PP4. The decisive discrepancy is
   PVS1 strength: two gold Strong items yield P, while predicted Strong + Moderate
   yields LP. This is a criteria-spec/coverage disagreement, not metric arithmetic.

10. **`NM_001114753.3:c.-9G>A` — VUS -> LB.** Gold records
    PS3_Supporting + BP5 and explicitly says PM2 is not met. The pipeline instead
    applied BS1_Supporting + BP4_Supporting, which directly yields LB. PS3 had no
    retrieved experiments and BP5 is unscheduled. The BS1 disagreement is likely
    evidence drift: the batch used FAF95 0.00091619, just above the 0.0008
    Supporting threshold, while the gold summary cites AF 0.0007942, just below
    it. BP4 was applied to a 5' UTR variant from SpliceAI=0 even though the local
    PlanRAG applicability prose and variant-type configuration are not fully
    consistent for UTR variants.

11. **`NM_000020.3:c.1348A>G` — LB -> VUS.** Gold says BS1 at Strong;
    the pipeline applied BS1 only at benign Supporting. The batch used popmax FAF
    0.001739, below the 0.002 Strong cutoff, while the gold summary cites an
    Ashkenazi filtering AF of 0.004015. This population/database/measure difference
    changes the strength. One benign Strong item yields LB; one benign Supporting
    item remains VUS.

12. **`NM_000020.3:c.88C>T` — LB -> VUS.** Gold classification depends
    on BP5 + BP2. Both are patient-level co-occurrence/phasing criteria and neither
    is in the automated HHT schedule. The pipeline applied no criteria, so VUS is
    the correct result for the incomplete predicted evidence set.

13. **`NM_000020.3:c.706G>A` — P -> LP.** Gold has PP1_Strong,
    PM2_Supporting, PS4_Strong, and PP3. The pipeline found every automated item
    but PP1 is manual/deferred and unscheduled. Predicted PS4_Strong + PM2 + PP3
    yields LP; adding PP1_Strong gives two Strong items and P.

14. **`NM_001278138.2:c.270+3G>T` — LB -> VUS.** Gold has
    PM2_Supporting + BP5 + BP4. The pipeline found PM2 and additionally applied
    PS4_Supporting, but it found no benign criteria. BP5 is unscheduled and BP4 is
    absent from this result, apparently because VEP consequence-to-variant-type
    filtering removed it; the gold summary's SpliceAI value would otherwise support
    BP4. Without BP5 + BP4, the benign override that yields LB cannot fire.

15. **`NM_001114753.3:c.447G>C` — P -> LP.** Gold has PP4_Moderate,
    PM2_Supporting, PS3_Supporting, PS4_Strong, PP1, and PP3. The pipeline found
    PM2, PS4_Strong, and PP3. PS3 returned no experiments; PP4 and PP1 are
    unscheduled. Predicted Strong + 2 Supporting yields LP; the gold Moderate plus
    two additional Supporting items raise it to P.

## Technical failures in dedicated 48-target attempts

This is distinct from the 15 final-class mismatches above.

- `batch_20260717_164439` is the newest attempt, but it stopped after 1/48. Its
  single result succeeded; the other 47 variants are absent, and the summary stores
  no reason for why the run stopped.
- `batch_20260717_163712` also stopped after 1/48 with no recorded per-variant
  exception for the unprocessed rows.
- `batch_20260717_154948` reached 6/48 and recorded three explicit failures:
  - `NM_000020.3:c.484C>T`: `RemoteProtocolError: Server disconnected without
    sending a response.`
  - `NM_000020.3:c.151T>G`: `RemoteProtocolError: Server disconnected without
    sending a response.`
  - `NM_000020.3:c.266G>T`: Gemini `RESOURCE_EXHAUSTED` / HTTP 429.

The remaining variants in those interrupted attempts are missing, not explicitly
failed, so their failure reasons cannot be recovered from `batch_summary.json`.

