## Case Study: Why Did the Question 3 Ablation Accuracy Improve Between Runs? (Judge-Agent Stochasticity, Not a Code Fix)

### Motivation

Two ablation studies (`evaluation/question3.py`) were run over the identical 25-variant HHT gold set (`hht_script_2.csv`), with identical pipeline code, identical prompts, and identical combining rules. The first run (`ablation_summary_20260708_103554.json`) and the second run (`ablation_summary_20260708_122945.json`) produced very different aggregate accuracy:

| Mode | Run 1 (`103554`) Accuracy | Run 2 (`122945`) Accuracy |
|---|---|---|
| `full` | 0.600 | 0.880 |
| `no_debug` | 0.640 | 0.920 |
| `no_judge` | 0.760 | 0.920 |
| `task_only` | 0.680 | 0.920 |

It would be tempting to attribute this jump to a code change — and a code change did happen in between (a `KeyError`-inducing field-name mismatch between `judge_agent.py`/`check_agent.py` and the `CheckReasoningResult`/`CheckTechnicalResult` Pydantic schemas, which briefly caused every single criterion to error out with `ERROR: 'pass'` before being fixed by standardizing the field name to `passed`). But that fix was purely a dict-key rename — it did not touch any prompt text, model choice, temperature, retry logic, or combining-rule table. Functionally, Run 1 and Run 2 executed the exact same decision logic against the exact same LLM. This case study traces the accuracy difference to its actual source: **run-to-run stochasticity in the Judge agent's semantic reasoning check**, not a logic improvement — and shows direct evidence of that stochasticity captured within Run 2 itself.

---

### The three modes without a Judge-Debug interaction converged to identical predictions in Run 2

In Run 2, `no_debug`, `no_judge`, and `task_only` produced **byte-for-byte identical predictions on all 25 variants** (confirmed by diffing `ablation_raw_20260708_122945.json` variant-by-variant), despite each mode invoking a different combination of agents. This means that, in this particular run, the Task agent's first-shot output was already correct for 24 of 25 variants — no retry or reasoning check from Debug or Judge changed the outcome. In Run 1, these same three modes produced *different* accuracies from each other (0.640, 0.760, 0.680), meaning the Task agent's first-shot output was not universally sufficient — some retries and corrections mattered, and mattered differently in each mode's path.

This is the first piece of direct evidence that the two runs are not comparable as "before/after a fix" — they represent two different underlying samples of LLM behavior on nominally the same inputs, since with unchanged code neither the Task agent's zero-retry output nor the Judge's behavior should differ between runs unless the model's sampling itself varied.

---

### Direct evidence of the mechanism, captured within Run 2's own debug log

With `PIPELINE_DEBUG_LOG` enabled for Run 2, the log captured every Task-agent output and Judge verdict, including retries. `NM_001114753.3:c.1517T>A` (gold `LP`, driven by `PS4_Moderate`) is the one variant that still failed in Run 2's `full` mode, and its log entries show the mechanism directly.

Both the `full` mode's Judge check and the `no_debug` mode's Judge check on this same variant's `PS4` criterion **start from the identical first rejection**:

> Attempt 0 (both modes): Judge rejects with *"Incomplete source querying / evidence reporting,"* Task's `applies=True`.

From that identical starting point, the two paths diverge:

- **`no_debug` (Task → Judge, no Debug):** Attempt 1 — Judge accepts (*"correctly extracted..."*). Resolved in one retry.
- **`full` (Debug → Judge):** Attempts 1 through 5 (the full `RETRY_LIMIT`) oscillate between two *different* rejection reasons — *"Incomplete source querying / evidence reporting"* (with `applies=True`) and *"Incorrect tool_used value"* (with `applies=False`) — flip-flopping without ever satisfying both objections at once. The criterion is still failing after the final retry-limit check, and `PS4` is marked as failed for this variant in `full` mode, which is what drops the final call from `LP` to `VUS`.

The Judge is not applying a stable, repeatable standard to near-identical Task-agent output; it raises a different objection on different calls, so the Task agent's retry loop chases a moving target. Whether this resolves in one attempt (as it happened to in `no_debug`) or spirals through all five retries without resolving (as it happened to in `full`) is a matter of which specific rejection the Judge happens to surface on a given call — i.e., sampling variance in the Judge's own LLM call, not a deterministic function of which agents are active.

---

### Answering the question: why did accuracy improve?

**It improved because Run 2 happened to be a "luckier" draw of Judge-agent behavior than Run 1, not because any reasoning logic was fixed.** In Run 1, whatever the Judge's sampling produced that day caused it to genuinely destabilize 5 of the 25 variants relative to what a Debug-only or Task-only path would have gotten right (the `no_judge` vs. `full` comparison in Run 1 showed exactly this: `no_judge` at 0.760 vs. `full` at 0.600, a 4-variant gap). In Run 2, the same Judge logic, run again on the same variants, only destabilized 1 of 25. The single remaining failure in Run 2 (`c.1517T>A`) is a clean, captured example of exactly the same failure mode that (most likely) accounted for several of Run 1's five failures — the Judge oscillating between contradictory objections until it exhausts its retry budget — just occurring at a much lower rate on this particular run.

The intervening bug fix (the `past`→`passed` field-name correction) is a red herring for explaining this specific accuracy change: it only affected an intermediate, fully-broken run (100% `ERROR` predictions, not shown in the table above) that sat between Run 1 and Run 2, and it made no change to any prompt, threshold, or agent-decision code. Both Run 1 and Run 2 reflect the same underlying (still only partially reliable) Judge-agent behavior; they simply landed on different sides of its variance.

---

### Synthesis

This case study's main finding is a methodological one as much as a technical one: **a single ablation run is not sufficient to characterize the Judge agent's net effect**, because its impact is dominated by a stochastic, retry-oscillation failure mode whose incidence rate varies materially from run to run (4-variant net cost in Run 1; roughly 1-variant net cost in Run 2) even with zero code changes in between. The captured debug log shows this is not noise in the aggregate metric alone — it is visible at the level of a single criterion on a single variant, where an identical first-round rejection led to quick resolution in one code path and unresolved oscillation in another. Any claim about whether the Judge agent helps, hurts, or is neutral should be based on multiple independent ablation runs (or a fixed-seed/temperature-0 configuration for the Judge's `check_reasoning` call) rather than a single run's numbers — and the fact that `no_debug`, `no_judge`, and `task_only` converged to identical predictions in Run 2 suggests that, on this gold set, the Task agent's first-shot accuracy is already high enough that the added agents' main measurable effect is this occasional destabilization rather than a reliable net improvement.
