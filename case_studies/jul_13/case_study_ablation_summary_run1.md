## Case Study: `ablation_summary_RUN1.json` — Agents Amplify a Conservative-Downgrade Bias Instead of Correcting It

### Source data

`evaluation/outputs/ablation_summary_RUN1.json` (aggregate metrics) and `evaluation/outputs/ablation_raw_RUN1.json` (per-variant predictions), a 200-variant, 5-class (B / LB / VUS / LP / P) ACMG classification ablation across four pipeline configurations:

| Mode | Agents active | Accuracy | Macro F1 |
|---|---|---|---|
| `full` | Task + Debug + Judge | 0.455 | 0.496 |
| `no_debug` | Task + Judge | 0.505 | 0.538 |
| `no_judge` | Task + Debug | 0.515 | 0.546 |
| `task_only` | Task alone | 0.510 | 0.542 |

The headline result is counterintuitive: the fully-assembled pipeline (`full`) scores *worst* of the four modes, and the bare `task_only` agent is essentially tied with the two partial configurations. Adding review agents did not net-improve classification accuracy on this dataset — it made it slightly worse.

---

### The dominant error pattern is identical across all four modes

Diffing `gold` vs `pred` per mode shows the same two error types account for the overwhelming majority of mistakes in every configuration:

| Mode | `P → LP` errors | `LB → VUS` errors | Total errors |
|---|---|---|---|
| `full` | 47 / 64 P variants | 31 / 58 LB variants | 109 |
| `no_debug` | 45 / 64 | 23 / 58 | 99 |
| `no_judge` | 43 / 64 | 23 / 58 | 97 |
| `task_only` | 44 / 64 | 23 / 58 | 98 |

In other words, roughly 70% of truly-Pathogenic variants get called Likely Pathogenic, and 40-53% of truly-Likely-Benign variants get called VUS, in *every* mode. This shows up directly in the classification reports: `P` recall is only 0.078–0.109 across all four modes despite 1.000 precision (the model essentially never over-calls `P`, it just almost never commits to it), and `LB` recall ranges 0.47–0.60 with ~0.93–0.95 precision. The model is not making random mistakes — it has a systematic bias toward the next-less-confident label, treating "confident" classifications (`P`, `LB`) as needing more evidence than the gold standard requires, and defaulting one notch toward the ambiguous middle (`LP`, `VUS`).

---

### Adding Debug and Judge agents doesn't fix this bias — it exaggerates it

Diffing predictions variant-by-variant between modes isolates what each agent actually changes:

**`no_judge` → `full` (adding the Debug agent on top of Task+Judge):** 12 variants flip, and every single flip moves toward a less-confident label — `LP→VUS`, `P→LP`, `LB→VUS` (e.g., 7 of the 12 are `LB→VUS` on `NM_001114753.3` transcript variants alone). None flip toward a more accurate, more confident label.

**`no_debug` → `no_judge` (removing the Judge agent):** only 4 variants flip, again all in the conservative direction when the Judge is added back (`LP→VUS`, `P→VUS`).

**`task_only` → `no_judge` (adding the Debug agent to the bare Task agent):** 4 variants flip, same pattern — `P→VUS`, `LP→VUS`.

So both additional agents (Debug and Judge) independently push predictions in the *same* direction: away from the gold label and toward one step less confident. Since the base Task-only bias is already toward under-confidence (the `P→LP`/`LB→VUS` pattern above), each additional review layer compounds it rather than catching and correcting it. This is consistent with the July 8 ablation finding for the 25-variant HHT set (`case_study_question3_ablation_accuracy_change.md`) that the Judge agent's checks are not a stable, symmetric correction mechanism — but here the effect is directional rather than merely noisy: on this 200-variant set, Debug and Judge don't destabilize predictions randomly, they consistently nudge them toward more conservative calls.

---

### Why this matters

1. **The bottleneck is the Task agent's base calibration, not agent orchestration.** Since all four modes share the same ~70% `P→LP` and ~45% `LB→VUS` error rates, no combination of review agents evaluated here fixes the core problem — the underlying evidence-weighing (likely how strongly PS4/PM2/BS3/etc. combine into a final call) is systematically too conservative before Debug or Judge ever run.
2. **Debug and Judge should not be assumed to be "safety nets."** On this run, their net measurable effect is negative for aggregate accuracy: `full` (both agents) is 6 points worse than `task_only` (no agents at all). Any future claim that adding review agents improves classification quality should be checked against this — on this dataset it doesn't, and where it changes predictions, it moves them further from gold, not closer.
3. **This is a different failure mode from the July 8 Judge-stochasticity finding.** July 8 showed the Judge oscillating unpredictably between contradictory objections on a single criterion (noise). Here, across many more variants, the shift is one-directional (bias) — worth distinguishing when deciding whether the fix is "reduce retry/oscillation" (a reliability fix) versus "recalibrate what evidence threshold the agents demand before accepting a strong criterion/label" (a calibration fix). The evidence in this run points more toward the latter.
