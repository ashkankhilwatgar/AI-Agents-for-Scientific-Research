"""
HHT VCEP variant classification scoring module.

Implements the CSpec GN135 v1.1.0 combining criteria rules.
Source: https://cspec.genome.network/cspec/ui/svi/doc/GN135#rules-combinations-panel-1576018580

Inputs:
    results_dict — dict mapping criterion key (e.g. "PM2_SUPPORTING") to the
                   result dict produced by the pipeline. Each result must have:
                     - "applies": bool
                     - "applied_strength": str  (set by task_agent.py)
                     - "status": str

Outputs:
    classify() returns:
        {
            "classification": str,   # Pathogenic | Likely Pathogenic | VUS | Likely Benign | Benign
            "rule_matched": str,     # human-readable description of the matched rule
            "buckets": dict,         # counts per bucket (vs, s, m, sup, ba, bs, bsup)
            "applied_criteria": list[str],  # criteria that contributed to buckets
            "incompatibility_notes": list[str],  # any downgrade actions taken
        }
"""

from data.planrag import query as planrag_query


def _get_scoring_entry(disease: str = None) -> dict:
    return planrag_query("SCORING", disease=disease)


def _get_bucket(criterion: str, applied_strength: str, scoring: dict) -> str | None:
    """
    Map a criterion + applied_strength to a bucket string.
    Returns None if the criterion/strength combo is unrecognised.
    """
    # Fixed-strength criteria first
    fixed = scoring.get("fixed_strengths", {})
    if criterion in fixed:
        return fixed[criterion]

    # Variable-strength criteria — map the applied_strength string to a bucket
    var_map = scoring.get("variable_strength_map", {})
    return var_map.get(applied_strength)


def _apply_incompatibilities(
    applied: dict[str, dict],
    scoring: dict,
) -> tuple[dict[str, dict], list[str]]:
    """
    Apply incompatibility rules (e.g. PM1 + PM5_Strong → downgrade PM5 to Moderate).
    Returns a (possibly modified) copy of applied and a list of notes.

    applied: {criterion_key: result_dict}
    """
    applied = {k: dict(v) for k, v in applied.items()}  # shallow copy
    notes = []

    for rule in scoring.get("incompatible_combinations", []):
        criteria = rule.get("criteria", [])

        # Check if all criteria in the rule are present and applied
        if not all(applied.get(c, {}).get("applies") for c in criteria):
            continue

        # Evaluate condition string (simple interpreter — only handles applied_strength comparisons)
        condition = rule.get("condition", "")
        target = rule.get("target")
        target_result = applied.get(target, {})

        if "applied_strength ==" in condition:
            # e.g. "PM5 applied_strength == strong"
            _, rhs = condition.split("==")
            required_strength = rhs.strip().strip("'\"")
            if target_result.get("applied_strength") != required_strength:
                continue  # condition not met

        # Apply action
        action = rule.get("action")
        if action == "downgrade":
            new_strength = rule.get("new_strength")
            applied[target]["applied_strength"] = new_strength
            notes.append(
                f"{rule.get('note', f'{target} downgraded to {new_strength}')} "
                f"(was {required_strength})"
            )

    return applied, notes


def _check_rule(rule: dict, counts: dict) -> bool:
    """
    Return True if all minimum counts in rule are satisfied by counts.
    Rule keys: vs, s, m, sup, ba, bs, bsup. Missing keys default to 0.
    """
    for bucket, minimum in rule.items():
        if bucket == "label":
            continue
        if counts.get(bucket, 0) < minimum:
            return False
    return True


def classify(results_dict: dict, disease: str = None) -> dict:
    """
    Classify a variant using the appropriate combining criteria rules.

    Routes to ACMG_PLANRAG_DB SCORING when disease is non-null and not a VCEP disease,
    otherwise uses PLANRAG_DB SCORING (HHT VCEP). Backward compatible: disease=None → HHT.

    results_dict: mapping of criterion_key → pipeline result dict.
    Each result must have "applies" (bool) and "applied_strength" (str).
    """
    scoring = _get_scoring_entry(disease=disease)
    if scoring is None:
        return {
            "classification": "Error",
            "rule_matched":   "SCORING entry not found in planrag",
            "buckets": {},
            "applied_criteria": [],
            "incompatibility_notes": [],
        }

    # ── 1. Filter to applied, non-error, non-skipped criteria ─────────────────
    applied = {
        k: v for k, v in results_dict.items()
        if v.get("applies") is True and v.get("status") not in ("error", "skipped")
    }

    # ── 2. Apply incompatibility rules (may downgrade applied_strength) ────────
    applied, incompat_notes = _apply_incompatibilities(applied, scoring)

    # ── 3. Bucket each applied criterion ──────────────────────────────────────
    counts = {"vs": 0, "s": 0, "m": 0, "sup": 0, "ba": 0, "bs": 0, "bsup": 0}
    bucket_of = {}  # criterion → bucket (for reporting)
    unrecognised = []

    bucket_to_count_key = {
        "very_strong":        "vs",
        "strong":             "s",
        "moderate":           "m",
        "supporting":         "sup",
        "benign_stand_alone": "ba",
        "benign_strong":      "bs",
        "benign_supporting":  "bsup",
    }

    for criterion, result in applied.items():
        strength = result.get("applied_strength")
        bucket = _get_bucket(criterion, strength, scoring)
        if bucket is None:
            unrecognised.append(f"{criterion} (applied_strength={strength!r})")
            continue
        count_key = bucket_to_count_key.get(bucket)
        if count_key:
            counts[count_key] += 1
            bucket_of[criterion] = bucket

    applied_criteria = list(bucket_of.keys())

    # ── 4. Check benign rules first (override pathogenic) ─────────────────────
    for rule in scoring.get("benign_rules", []):
        if _check_rule(rule, counts):
            return {
                "classification":       "Benign",
                "rule_matched":         rule["label"],
                "buckets":              counts,
                "bucket_detail":        bucket_of,
                "applied_criteria":     applied_criteria,
                "incompatibility_notes": incompat_notes,
                "unrecognised_criteria": unrecognised,
            }

    # ── 5. Check pathogenic rules ─────────────────────────────────────────────
    for rule in scoring.get("pathogenic_rules", []):
        if _check_rule(rule, counts):
            return {
                "classification":       "Pathogenic",
                "rule_matched":         rule["label"],
                "buckets":              counts,
                "bucket_detail":        bucket_of,
                "applied_criteria":     applied_criteria,
                "incompatibility_notes": incompat_notes,
                "unrecognised_criteria": unrecognised,
            }

    # ── 6. Check likely pathogenic rules ──────────────────────────────────────
    for rule in scoring.get("likely_pathogenic_rules", []):
        if _check_rule(rule, counts):
            return {
                "classification":       "Likely Pathogenic",
                "rule_matched":         rule["label"],
                "buckets":              counts,
                "bucket_detail":        bucket_of,
                "applied_criteria":     applied_criteria,
                "incompatibility_notes": incompat_notes,
                "unrecognised_criteria": unrecognised,
            }

    # ── 7. Check likely benign rules ──────────────────────────────────────────
    for rule in scoring.get("likely_benign_rules", []):
        if _check_rule(rule, counts):
            return {
                "classification":       "Likely Benign",
                "rule_matched":         rule["label"],
                "buckets":              counts,
                "bucket_detail":        bucket_of,
                "applied_criteria":     applied_criteria,
                "incompatibility_notes": incompat_notes,
                "unrecognised_criteria": unrecognised,
            }

    # ── 8. VUS — no rules matched ─────────────────────────────────────────────
    return {
        "classification":       "Variant of Uncertain Significance (VUS)",
        "rule_matched":         "No combining criteria rule was satisfied",
        "buckets":              counts,
        "bucket_detail":        bucket_of,
        "applied_criteria":     applied_criteria,
        "incompatibility_notes": incompat_notes,
        "unrecognised_criteria": unrecognised,
    }
