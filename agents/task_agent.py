import re
import requests
import json
# from config import MODELS, OLLAMA_BASE_URL
from tools.vep import annotate_variant
from tools.clinvar import search_clinvar, search_clinvar_for_codon, search_clinvar_for_variant_ps4, search_clinvar_for_exact_variant
from tools.gnomad import query_gnomad, query_gnomad_gene_constraint
from tools.utils import hgvs_to_gnomad_format
from tools.computational import query_revel_spliceai, query_spliceai
from tools.vep import annotate_variant, _check_repeat_region, check_pm1_critical_region
from tools.pubmed import search_pubmed
from tools.erepo import search_erepo_by_position, search_erepo_for_variant
from tools.lovd import search_lovd_for_variant
from data.planrag import query, get_gene_from_transcript, GENE_DB
from .llm.llm import create_llm
from typing import Optional, Any, TypeAlias
from config import MODELS
from pydantic import BaseModel
from .llm.response_schema import TaskInterpretation, ToolDecision
from typing import TypeVar
from rich.console import Console
from rich.text import Text

# Local type alias (avoids importing from pipeline, which would create a circular import)
ToolResults: TypeAlias = dict[str, dict[str, Any]]
task_console = Console()


def _task_warning(message: str) -> None:
    """Render an actionable task-agent warning as one styled line."""
    warning = Text()
    warning.append("⚠ Task agent: ", style="bold yellow")
    warning.append(message)
    task_console.print(warning)

# OLLAMA_GENERATE_URL = f"{OLLAMA_BASE_URL}/api/generate"


# def _annotate_gnomad_frequency(result: dict) -> dict:
#     """
#     Pre-computes frequency threshold verdicts on a gnomAD result dict and injects
#     a '_computed' summary so the LLM reads pre-verified verdicts rather than
#     performing floating-point comparisons itself (LLMs reliably mis-compare
#     scientific notation, e.g. concluding 5.3e-05 >= 1e-04).

#     Adds '_computed' with:
#         pm2_applies, ba1_applies, bs1_applies, bs2_check_ac_hom, verdicts (str)
#     """
#     if "error" in result or not result.get("found", True):
#         result = dict(result)
#         result["_computed"] = {
#             "absent_from_gnomad": True,
#             "total_ac": 0,
#             "max_subpop_af": 0.0,
#             "popmax_faf": 0.0,
#             "ac_hom": 0,
#             "pm2_applies": True,
#             "ba1_applies": False,
#             "bs1_applies": False,
#             "bs2_check_ac_hom": False,
#             "verdicts": (
#                 "Variant ABSENT from gnomAD. "
#                 "PM2: APPLIES (absent). BA1: DOES NOT APPLY. "
#                 "BS1: DOES NOT APPLY. BS2: ac_hom=0 → DOES NOT APPLY for dominant."
#             ),
#         }
#         return result

#     result = dict(result)
#     total_ac   = result.get("total_ac", 0) or 0
#     popmax_faf = result.get("popmax_faf", 0.0) or 0.0
#     ac_hom     = result.get("ac_hom", 0) or 0

#     # Compute max raw subpopulation AF for reference only (not used for PM2 decision).
#     # Raw per-population AC/AN can be misleading for rare variants — a single allele
#     # in a small subpopulation cohort inflates AF (e.g. AC=1, AN=3663 → AF=2.73e-4
#     # even when overall AF is 4.7e-6). gnomAD's popmax_faf already accounts for this
#     # sampling uncertainty and is the recommended metric for clinical variant filtering.
#     all_subpop_afs = []
#     for src_key in ("exome", "genome"):
#         src = result.get(src_key) or {}
#         for pop in src.get("populations", []):
#             ac_p = pop.get("ac") or 0
#             an_p = pop.get("an") or 0
#             if an_p > 0:
#                 all_subpop_afs.append(ac_p / an_p)

#     max_subpop_af = max(all_subpop_afs) if all_subpop_afs else 0.0
#     absent = total_ac == 0

#     # Threshold decisions (computed in Python — not delegated to LLM)
#     # PM2 uses popmax_faf (gnomAD filtering allele frequency, 95% CI upper bound)
#     # rather than raw max subpopulation AF. popmax_faf is gnomAD's own recommended
#     # metric for clinical filtering and accounts for sampling uncertainty in small
#     # population cohorts that would otherwise inflate raw per-population AFs.
#     pm2_applies = absent or (popmax_faf < 0.0001)  # threshold: 1e-4
#     ba1_applies = popmax_faf >= 0.05
#     bs1_applies = (not ba1_applies) and (popmax_faf > 0.01)
#     ac_hom_present = ac_hom > 0

#     result["_computed"] = {
#         "absent_from_gnomad": absent,
#         "total_ac": total_ac,
#         "max_subpop_af": max_subpop_af,
#         "popmax_faf": popmax_faf,
#         "ac_hom": ac_hom,
#         "pm2_applies": pm2_applies,
#         "ba1_applies": ba1_applies,
#         "bs1_applies": bs1_applies,
#         "bs2_check_ac_hom": ac_hom_present,
#         "verdicts": (
#             f"COMPUTED VERDICTS — use these directly, do NOT recompute:\n"
#             f"  PM2 (threshold: popmax_FAF < 0.0001): popmax_FAF={popmax_faf:.6e} "
#             f"→ {'APPLIES' if pm2_applies else 'DOES NOT APPLY'}\n"
#             f"    (raw max subpop AF={max_subpop_af:.6e} — for reference only; "
#             f"popmax_FAF used for decision to account for sampling uncertainty)\n"
#             f"  BA1 (threshold: popmax_FAF >= 0.05): popmax_FAF={popmax_faf:.6f} "
#             f"→ {'APPLIES' if ba1_applies else 'DOES NOT APPLY'}\n"
#             f"  BS1 (threshold: popmax_FAF > 0.01): popmax_FAF={popmax_faf:.6f} "
#             f"→ {'APPLIES' if bs1_applies else 'DOES NOT APPLY'}\n"
#             f"  BS2: ac_hom={ac_hom} → {'present, check inheritance' if ac_hom_present else 'absent → DOES NOT APPLY for dominant/X-linked'}"
#         ),
#     }
#     return result


# def _annotate_gnomad_gene_constraint(result: dict) -> dict:
#     """
#     Pre-computes PP2/BP1 threshold verdicts on a gnomAD gene constraint result
#     and injects a '_computed' summary so the LLM reads pre-verified verdicts.

#     PP2 uses an objective threshold (mis_z >= 3.09) — computed here in Python.
#     BP1 requires clinical knowledge of disease mechanism, so constraint metrics
#     are provided with interpretation hints for the LLM.
#     """
#     if "error" in result:
#         return result

#     result = dict(result)
#     mis_z        = result.get("mis_z")
#     pLI          = result.get("pLI")
#     oe_lof_upper = result.get("oe_lof_upper")
#     oe_mis       = result.get("oe_mis")

#     pp2_threshold_met  = mis_z is not None and mis_z >= 3.09
#     lof_intolerant     = (pLI is not None and pLI >= 0.9) or (oe_lof_upper is not None and oe_lof_upper <= 0.35)
#     missense_tolerated = oe_mis is not None and oe_mis >= 0.8

#     mis_z_str        = f"{mis_z:.4f}"        if mis_z        is not None else "N/A"
#     pLI_str          = f"{pLI:.6f}"          if pLI          is not None else "N/A"
#     oe_lof_upper_str = f"{oe_lof_upper:.4f}" if oe_lof_upper is not None else "N/A"
#     oe_mis_str       = f"{oe_mis:.4f}"       if oe_mis       is not None else "N/A"

#     result["_computed"] = {
#         "pp2_threshold_met":  pp2_threshold_met,
#         "lof_intolerant":     lof_intolerant,
#         "missense_tolerated": missense_tolerated,
#         "verdicts": (
#             f"COMPUTED VERDICTS — use these directly, do NOT recompute:\n"
#             f"  PP2 (threshold: mis_z >= 3.09): mis_z={mis_z_str} "
#             f"→ {'THRESHOLD MET — PP2 applies IF missense is a known disease mechanism' if pp2_threshold_met else 'THRESHOLD NOT MET — PP2 does NOT apply'}\n"
#             f"  BP1 constraint profile: pLI={pLI_str}, LOEUF={oe_lof_upper_str}, oe_mis={oe_mis_str}\n"
#             f"    LOF intolerant (pLI>=0.9 or LOEUF<=0.35): {lof_intolerant} "
#             f"→ {'LOF-constrained gene — LOF likely causes disease; BP1 could apply if missense not primary mechanism' if lof_intolerant else 'Gene tolerates LOF — BP1 unlikely (LOF not primary disease mechanism)'}\n"
#             f"    Missense tolerated (oe_mis>=0.8): {missense_tolerated} "
#             f"→ {'missense common in healthy population → supports BP1 if LOF is primary disease mechanism' if missense_tolerated else 'missense constrained → gene does not tolerate missense → BP1 unlikely'}"
#         ),
#     }
#     return result


# def _annotate_spliceai(result: dict) -> dict:
#     """
#     Pre-computes PP3/BP4 threshold verdicts on a revel_spliceai result dict and
#     injects a '_computed' summary so the LLM reads pre-verified verdicts rather
#     than re-examining individual score values (LLMs systematically fail to read
#     score arrays correctly, e.g. concluding DS_DL=0.99 does not exceed 0.2).

#     Thresholds computed:
#       PP3: REVEL >= 0.644 (ClinGen SVI calibrated) OR any SpliceAI score >= 0.2
#       BP4: REVEL <= 0.290 (ACMG) / <= 0.15 (HHT VCEP) AND all SpliceAI scores <= 0.1
#     """
#     if "error" in result:
#         return result

#     result = dict(result)

#     revel   = result.get("revel_score")
#     ds_ag   = result.get("DS_AG")
#     ds_al   = result.get("DS_AL")
#     ds_dg   = result.get("DS_DG")
#     ds_dl   = result.get("DS_DL")

#     # Collect non-None SpliceAI scores
#     scores = {k: v for k, v in [("DS_AG", ds_ag), ("DS_AL", ds_al),
#                                   ("DS_DG", ds_dg), ("DS_DL", ds_dl)] if v is not None}

#     above_02     = {k: v for k, v in scores.items() if v >= 0.2}   # PP3 trigger
#     above_01     = {k: v for k, v in scores.items() if v > 0.1}    # BP4 fail
#     spliceai_max = max(scores.values()) if scores else None

#     spliceai_pp3_fires   = bool(above_02)
#     spliceai_bp4_passes  = bool(scores) and not above_01   # all present scores <= 0.1

#     # REVEL threshold decisions (all computed here — not delegated to LLM)
#     revel_pp3_applies      = revel is not None and revel >= 0.644
#     revel_bp4_acmg_passes  = revel is not None and revel <= 0.290
#     revel_bp4_hht_passes   = revel is not None and revel <= 0.15

#     # Build human-readable scores display line
#     scores_display = ", ".join(
#         f"{k}={'N/A' if v is None else f'{v:.4f}'}"
#         for k, v in [("DS_AG", ds_ag), ("DS_AL", ds_al), ("DS_DG", ds_dg), ("DS_DL", ds_dl)]
#     )

#     # SpliceAI PP3 verdict
#     if spliceai_pp3_fires:
#         splice_pp3_str = f"FIRES — triggering score(s): {', '.join(f'{k}={v:.4f}' for k, v in above_02.items())}"
#     elif spliceai_max is not None:
#         splice_pp3_str = f"DOES NOT FIRE (max score={spliceai_max:.4f}, all < 0.2)"
#     else:
#         splice_pp3_str = "N/A (SpliceAI scores not available)"

#     # SpliceAI BP4 verdict
#     if not scores:
#         splice_bp4_str = "N/A (SpliceAI scores not available)"
#     elif spliceai_bp4_passes:
#         splice_bp4_str = f"PASSES (all scores <= 0.1, max={spliceai_max:.4f})"
#     else:
#         splice_bp4_str = f"FAILS — score(s) above 0.1: {', '.join(f'{k}={v:.4f}' for k, v in above_01.items())}"

#     # REVEL verdict helpers
#     def _revel_verdict(applies: bool | None, label: str) -> str:
#         if revel is None:
#             return "N/A (REVEL not available)"
#         return f"{'APPLIES' if applies else 'DOES NOT APPLY'} (score={revel:.4f})"

#     def _revel_bp4_verdict(passes: bool | None, threshold_str: str) -> str:
#         if revel is None:
#             return "N/A"
#         return f"{'PASSES' if passes else 'FAILS'} (score={revel:.4f})"

#     result["_computed"] = {
#         "spliceai_pp3_fires":    spliceai_pp3_fires,
#         "spliceai_bp4_passes":   spliceai_bp4_passes,
#         "revel_pp3_applies":     revel_pp3_applies,
#         "revel_bp4_acmg_passes": revel_bp4_acmg_passes,
#         "revel_bp4_hht_passes":  revel_bp4_hht_passes,
#         "verdicts": (
#             f"COMPUTED VERDICTS — read these directly, do NOT re-examine or recompute from raw scores:\n"
#             f"  SpliceAI scores: {scores_display}\n"
#             f"  PP3 SpliceAI (any score >= 0.2): {splice_pp3_str}\n"
#             f"  BP4 SpliceAI (all scores <= 0.1): {splice_bp4_str}\n"
#             f"  REVEL score: {'N/A' if revel is None else f'{revel:.4f}'}\n"
#             f"  PP3 REVEL (>= 0.644): {_revel_verdict(revel_pp3_applies, '>=0.644')}\n"
#             f"  BP4 REVEL ACMG threshold (<= 0.290): {_revel_bp4_verdict(revel_bp4_acmg_passes, '<=0.290')}\n"
#             f"  BP4 REVEL HHT threshold (<= 0.15):   {_revel_bp4_verdict(revel_bp4_hht_passes, '<=0.15')}"
#         ),
#     }
#     return result


def _annotate_gnomad_frequency(result: dict) -> dict:
    """
    Pre-computes frequency threshold verdicts on a gnomAD result dict and injects
    a '_computed' summary so the LLM reads pre-verified verdicts rather than
    performing floating-point comparisons itself (LLMs reliably mis-compare
    scientific notation, e.g. concluding 5.3e-05 >= 1e-04).

    Adds '_computed' with:
        pm2_applies, ba1_applies, bs1_applies, bs2_check_ac_hom, verdicts (str)
    """
    if "error" in result or not result.get("found", True):
        result = dict(result)
        result["_computed"] = {
            "absent_from_gnomad": True,
            "total_ac": 0,
            "max_subpop_af": 0.0,
            "popmax_faf": 0.0,
            "ac_hom": 0,
            "pm2_applies": True,
            "ba1_applies": False,
            "bs1_applies": False,
            "bs2_check_ac_hom": False,
            "verdicts": (
                "Variant ABSENT from gnomAD. "
                "PM2: APPLIES (absent). BA1: DOES NOT APPLY. "
                "BS1: DOES NOT APPLY. BS2: ac_hom=0 → DOES NOT APPLY for dominant."
            ),
        }
        return result

    result = dict(result)
    total_ac   = result.get("total_ac", 0) or 0
    popmax_faf = result.get("popmax_faf", 0.0) or 0.0
    ac_hom     = result.get("ac_hom", 0) or 0

    # Compute max raw subpopulation AF for reference only (not used for PM2 decision).
    # Raw per-population AC/AN can be misleading for rare variants — a single allele
    # in a small subpopulation cohort inflates AF (e.g. AC=1, AN=3663 → AF=2.73e-4
    # even when overall AF is 4.7e-6). gnomAD's popmax_faf already accounts for this
    # sampling uncertainty and is the recommended metric for clinical variant filtering.
    all_subpop_afs = []
    for src_key in ("exome", "genome"):
        src = result.get(src_key) or {}
        for pop in src.get("populations", []):
            ac_p = pop.get("ac") or 0
            an_p = pop.get("an") or 0
            if an_p > 0:
                all_subpop_afs.append(ac_p / an_p)

    max_subpop_af = max(all_subpop_afs) if all_subpop_afs else 0.0
    absent = total_ac == 0

    # Threshold decisions (computed in Python — not delegated to LLM)
    # PM2 uses popmax_faf (gnomAD filtering allele frequency, 95% CI upper bound)
    # rather than raw max subpopulation AF. popmax_faf is gnomAD's own recommended
    # metric for clinical filtering and accounts for sampling uncertainty in small
    # population cohorts that would otherwise inflate raw per-population AFs.
    pm2_applies = absent or (popmax_faf < 0.0001)  # threshold: 1e-4
    ba1_applies = popmax_faf >= 0.05
    bs1_applies = (not ba1_applies) and (popmax_faf > 0.01)
    ac_hom_present = ac_hom > 0

    result["_computed"] = {
        "absent_from_gnomad": absent,
        "total_ac": total_ac,
        "max_subpop_af": max_subpop_af,
        "popmax_faf": popmax_faf,
        "ac_hom": ac_hom,
        "pm2_applies": pm2_applies,
        "ba1_applies": ba1_applies,
        "bs1_applies": bs1_applies,
        "bs2_check_ac_hom": ac_hom_present,
        "verdicts": (
            f"COMPUTED VERDICTS — use these directly, do NOT recompute:\n"
            f"  PM2 (threshold: popmax_FAF < 0.0001): popmax_FAF={popmax_faf:.6e} "
            f"→ {'APPLIES' if pm2_applies else 'DOES NOT APPLY'}\n"
            f"    (raw max subpop AF={max_subpop_af:.6e} — for reference only; "
            f"popmax_FAF used for decision to account for sampling uncertainty)\n"
            f"  BA1 (threshold: popmax_FAF >= 0.05): popmax_FAF={popmax_faf:.6f} "
            f"→ {'APPLIES' if ba1_applies else 'DOES NOT APPLY'}\n"
            f"  BS1 (threshold: popmax_FAF > 0.01): popmax_FAF={popmax_faf:.6f} "
            f"→ {'APPLIES' if bs1_applies else 'DOES NOT APPLY'}\n"
            f"  BS2: ac_hom={ac_hom} → {'present, check inheritance' if ac_hom_present else 'absent → DOES NOT APPLY for dominant/X-linked'}"
        ),
    }
    return result


def _annotate_gnomad_gene_constraint(result: dict) -> dict:
    """
    Pre-computes PP2/BP1 threshold verdicts on a gnomAD gene constraint result
    and injects a '_computed' summary so the LLM reads pre-verified verdicts.

    PP2 uses an objective threshold (mis_z >= 3.09) — computed here in Python.
    BP1 requires clinical knowledge of disease mechanism, so constraint metrics
    are provided with interpretation hints for the LLM.
    """
    if "error" in result:
        return result

    result = dict(result)
    mis_z        = result.get("mis_z")
    pLI          = result.get("pLI")
    oe_lof_upper = result.get("oe_lof_upper")
    oe_mis       = result.get("oe_mis")

    pp2_threshold_met  = mis_z is not None and mis_z >= 3.09
    lof_intolerant     = (pLI is not None and pLI >= 0.9) or (oe_lof_upper is not None and oe_lof_upper <= 0.35)
    missense_tolerated = oe_mis is not None and oe_mis >= 0.8

    mis_z_str        = f"{mis_z:.4f}"        if mis_z        is not None else "N/A"
    pLI_str          = f"{pLI:.6f}"          if pLI          is not None else "N/A"
    oe_lof_upper_str = f"{oe_lof_upper:.4f}" if oe_lof_upper is not None else "N/A"
    oe_mis_str       = f"{oe_mis:.4f}"       if oe_mis       is not None else "N/A"

    result["_computed"] = {
        "pp2_threshold_met":  pp2_threshold_met,
        "lof_intolerant":     lof_intolerant,
        "missense_tolerated": missense_tolerated,
        "verdicts": (
            f"COMPUTED VERDICTS — use these directly, do NOT recompute:\n"
            f"  PP2 (threshold: mis_z >= 3.09): mis_z={mis_z_str} "
            f"→ {'THRESHOLD MET — PP2 applies IF missense is a known disease mechanism' if pp2_threshold_met else 'THRESHOLD NOT MET — PP2 does NOT apply'}\n"
            f"  BP1 constraint profile: pLI={pLI_str}, LOEUF={oe_lof_upper_str}, oe_mis={oe_mis_str}\n"
            f"    LOF intolerant (pLI>=0.9 or LOEUF<=0.35): {lof_intolerant} "
            f"→ {'LOF-constrained gene — LOF likely causes disease; BP1 could apply if missense not primary mechanism' if lof_intolerant else 'Gene tolerates LOF — BP1 unlikely (LOF not primary disease mechanism)'}\n"
            f"    Missense tolerated (oe_mis>=0.8): {missense_tolerated} "
            f"→ {'missense common in healthy population → supports BP1 if LOF is primary disease mechanism' if missense_tolerated else 'missense constrained → gene does not tolerate missense → BP1 unlikely'}"
        ),
    }
    return result


def _annotate_spliceai(result: dict) -> dict:
    """
    Pre-computes PP3/BP4 threshold verdicts on a revel_spliceai result dict and
    injects a '_computed' summary so the LLM reads pre-verified verdicts rather
    than re-examining individual score values (LLMs systematically fail to read
    score arrays correctly, e.g. concluding DS_DL=0.99 does not exceed 0.2).

    Thresholds computed:
      PP3: REVEL >= 0.644 (ClinGen SVI calibrated) OR any SpliceAI score >= 0.2
      BP4: REVEL <= 0.290 (ACMG) / <= 0.15 (HHT VCEP) AND all SpliceAI scores <= 0.1
    """
    if "error" in result:
        return result

    result = dict(result)

    revel   = result.get("revel_score")
    ds_ag   = result.get("DS_AG")
    ds_al   = result.get("DS_AL")
    ds_dg   = result.get("DS_DG")
    ds_dl   = result.get("DS_DL")

    # Collect non-None SpliceAI scores
    scores = {k: v for k, v in [("DS_AG", ds_ag), ("DS_AL", ds_al),
                                  ("DS_DG", ds_dg), ("DS_DL", ds_dl)] if v is not None}

    above_02     = {k: v for k, v in scores.items() if v >= 0.2}   # PP3 trigger
    above_01     = {k: v for k, v in scores.items() if v > 0.1}    # BP4 fail
    spliceai_max = max(scores.values()) if scores else None

    spliceai_pp3_fires   = bool(above_02)
    spliceai_bp4_passes  = bool(scores) and not above_01   # all present scores <= 0.1

    # REVEL threshold decisions (all computed here — not delegated to LLM)
    revel_pp3_applies      = revel is not None and revel >= 0.644
    revel_bp4_acmg_passes  = revel is not None and revel <= 0.290
    revel_bp4_hht_passes   = revel is not None and revel <= 0.15

    # Build human-readable scores display line
    scores_display = ", ".join(
        f"{k}={'N/A' if v is None else f'{v:.4f}'}"
        for k, v in [("DS_AG", ds_ag), ("DS_AL", ds_al), ("DS_DG", ds_dg), ("DS_DL", ds_dl)]
    )

    # SpliceAI PP3 verdict
    if spliceai_pp3_fires:
        splice_pp3_str = f"FIRES — triggering score(s): {', '.join(f'{k}={v:.4f}' for k, v in above_02.items())}"
    elif spliceai_max is not None:
        splice_pp3_str = f"DOES NOT FIRE (max score={spliceai_max:.4f}, all < 0.2)"
    else:
        splice_pp3_str = "N/A (SpliceAI scores not available)"

    # SpliceAI BP4 verdict
    if not scores:
        splice_bp4_str = "N/A (SpliceAI scores not available)"
    elif spliceai_bp4_passes:
        splice_bp4_str = f"PASSES (all scores <= 0.1, max={spliceai_max:.4f})"
    else:
        splice_bp4_str = f"FAILS — score(s) above 0.1: {', '.join(f'{k}={v:.4f}' for k, v in above_01.items())}"

    # REVEL verdict helpers
    def _revel_verdict(applies: bool | None, label: str) -> str:
        if revel is None:
            return "N/A (REVEL not available)"
        return f"{'APPLIES' if applies else 'DOES NOT APPLY'} (score={revel:.4f})"

    def _revel_bp4_verdict(passes: bool | None, threshold_str: str) -> str:
        if revel is None:
            return "N/A"
        return f"{'PASSES' if passes else 'FAILS'} (score={revel:.4f})"

    result["_computed"] = {
        "spliceai_pp3_fires":    spliceai_pp3_fires,
        "spliceai_bp4_passes":   spliceai_bp4_passes,
        "revel_pp3_applies":     revel_pp3_applies,
        "revel_bp4_acmg_passes": revel_bp4_acmg_passes,
        "revel_bp4_hht_passes":  revel_bp4_hht_passes,
        "verdicts": (
            f"COMPUTED VERDICTS — read these directly, do NOT re-examine or recompute from raw scores:\n"
            f"  SpliceAI scores: {scores_display}\n"
            f"  PP3 SpliceAI (any score >= 0.2): {splice_pp3_str}\n"
            f"  BP4 SpliceAI (all scores <= 0.1): {splice_bp4_str}\n"
            f"  REVEL score: {'N/A' if revel is None else f'{revel:.4f}'}\n"
            f"  PP3 REVEL (>= 0.644): {_revel_verdict(revel_pp3_applies, '>=0.644')}\n"
            f"  BP4 REVEL ACMG threshold (<= 0.290): {_revel_bp4_verdict(revel_bp4_acmg_passes, '<=0.290')}\n"
            f"  BP4 REVEL HHT threshold (<= 0.15):   {_revel_bp4_verdict(revel_bp4_hht_passes, '<=0.15')}"
        ),
    }
    return result


# def call_ollama(prompt: str) -> str:
#     payload = {
#         "model": MODELS["task"],
#         "prompt": prompt,
#         "stream": False,
#         "keep_alive": -1,
#         "options": {
#             "temperature": 0,
#             "num_predict": 1024
#         }
#     }
#     response = requests.post(OLLAMA_GENERATE_URL, json=payload)
#     response.raise_for_status()
#     return response.json()["response"]


def call_task_agent(prompt: str, output_schema: type[BaseModel]) -> BaseModel:
    """
    Invoke the task LLM and return its response as a structured Pydantic object.

    The output_schema defines the expected response shape. Because
    with_structured_output() is used, the returned value is an instance of that
    schema, not a raw chat message and not response.content.
    """
    llm = create_llm(
        model=MODELS["task"]["model"],
        provider=MODELS["task"]["provider"],
        temperature=0
    )
    structured_llm = llm.with_structured_output(output_schema)
    response = structured_llm.invoke([{"role": "user", "content": prompt}])
    
    return response


def select_tool(criterion: str, variant: str, disease: str | None = None, feedback: str | None = None) -> dict:
    """
    Called only on retry — first attempt always uses task["tool"] from the plan.
    feedback is the Judge agent's correction from the previous attempt.
    """
    feedback_block = ""
    if feedback:
        feedback_block = f"""
A previous attempt to evaluate this criterion failed with the following feedback:
{feedback}

Use this feedback to select the correct tool.
"""

    prompt = f"""You are a variant classification assistant applying ACMG/AMP 2015 criteria.

Your task is to evaluate criterion {criterion} for variant {variant} (disease: {disease or "unspecified"}).
{feedback_block}
You have access to the following tools:
- clinvar: searches ClinVar for variant classifications and proband counts. Use for PS4.
- gnomad: queries gnomAD for population allele frequency. Use for PM2, BA1, BS1, BS2.
- gnomad_gene: queries gnomAD for gene-level constraint metrics (missense Z-score, pLI, LOEUF). Use for PP2 and BP1.
- revel_spliceai: fetches REVEL score and SpliceAI delta scores. Use for PP3 and BP4.
- spliceai: fetches SpliceAI delta scores only. Use for BP7 (synonymous/intronic variants).
- vep: annotates variant consequence, codon position, and NMD prediction. Use for PVS1, PM1, PM4, BP3.
- pubmed: searches PubMed for case reports of the variant. Use for PS4 when ClinVar has no data.
- erepo: queries the ClinGen Evidence Repository for variants at the same protein position. Use for PS1 and PM5.
- lovd: queries the Leiden Open Variation Database for variant observations across labs. Use for PS4 when ClinVar and ERepo have no proband data.
- functional_evidence: queries the functional evidence tool for functional experiments & functional assays. Use for PS3 and BS3.

Use the provided output schema.

Important rules:
- The "tool" field shoule be the best tool for evaluating {criterion}
- In the "reason" field, you should give a brief explanation of why you choose that tool.
"""
    result = call_task_agent(prompt, ToolDecision).model_dump()

    # raw = call_ollama(prompt)
    return result


def run_tool(
        tool_decision: dict, 
        variant: str, 
        rag_entry: dict | None = None, 
        gene: str | None = None, 
        disease: str | None = None
) -> tuple[dict, str]:
    """
    Runs the selected tool and returns (result, actual_input_used).
    actual_input_used is the exact string passed to the API after any format conversion.
    """
    tool = tool_decision["tool"]
    input_value = variant

    # print(f"DEBUG - tool: {tool}, input: {input_value}")

    if tool == "clinvar":
        criterion = (rag_entry or {}).get("criterion", "")
        if criterion == "PS4":
            cdna_change = input_value.split(":")[-1] if ":" in input_value else input_value
            clinvar_ps4 = search_clinvar_for_variant_ps4(input_value)

            if clinvar_ps4.get("found") and clinvar_ps4.get("proband_count", 0) > 0:
                return clinvar_ps4, f"ClinVar VCEP SCV for {input_value}"

            # ERepo fallback — VCEP curated evidence may contain proband count
            # even when the ClinVar SCV comment field is empty
            erepo_ps4 = search_erepo_for_variant(gene, cdna_change)
            if "error" not in erepo_ps4 and erepo_ps4.get("found"):
                proband_count = erepo_ps4.get("proband_count")
                classification = erepo_ps4.get("classification") or ""
                # print(f"DEBUG - ERepo PS4: variant found | classification: {classification} | proband_count: {proband_count}")

                # If proband_count is not explicitly stated in the evidence notes,
                # infer it from the VCEP classification: P/LP requires patient-level evidence,
                # so treat it as ≥1 proband (PS4_Supporting threshold).
                if not proband_count:
                    if any(c in classification for c in ("Pathogenic", "Likely Pathogenic")):
                        proband_count = 1
                        # print(f"DEBUG - ERepo PS4: proband_count inferred as 1 from VCEP {classification} classification")

                # Only return ERepo as a PS4 source if we have usable proband data.
                # If classification is VUS (or other non-P/LP) and no explicit proband count,
                # ERepo has no useful PS4 evidence — fall through to LOVD.
                if proband_count and proband_count > 0:
                    return {
                        "found": True,
                        "proband_count": proband_count,
                        "source": "ClinGen ERepo",
                        "classification": classification,
                        "evidence_notes": erepo_ps4.get("evidence_notes"),
                        "proband_count_note": (
                            "Proband count inferred from VCEP classification (≥1 required for P/LP); "
                            "not explicitly stated in evidence notes."
                            if proband_count == 1 and not erepo_ps4.get("proband_count")
                            else None
                        ),
                    }, f"ERepo for {input_value}"

            # LOVD fallback — observation database across participating labs
            # Times_reported = number of independent lab submissions (proxy for probands)
            lovd_ps4 = search_lovd_for_variant(gene, cdna_change)
            if "error" not in lovd_ps4 and lovd_ps4.get("found"):
                times_reported = lovd_ps4.get("times_reported")
                # print(f"DEBUG - LOVD PS4: variant found | times_reported: {times_reported}")
                if times_reported and times_reported > 0:
                    return {
                        "found": True,
                        "proband_count": times_reported,
                        "source": "LOVD",
                        "classification": None,
                        "evidence_notes": (
                            f"Variant observed {times_reported} time(s) in LOVD "
                            f"(Leiden Open Variation Database). LOVD is an observation "
                            f"database — Times_reported reflects independent lab submissions, "
                            f"not VCEP-curated pathogenicity."
                        ),
                    }, f"LOVD for {input_value}"

            # PubMed fallback with protein + nucleotide notation
            disease_label = disease or "HHT"
            gene_label = gene or disease_label
            vep_result = annotate_variant(input_value)
            if "error" not in vep_result:
                protein_change   = vep_result.get("protein_change")
                protein_change_1 = vep_result.get("protein_change_1letter")
                if protein_change and protein_change_1:
                    pubmed_query = f"{gene_label} ({cdna_change} OR {protein_change} OR {protein_change_1}) {disease_label}"
                elif protein_change:
                    pubmed_query = f"{gene_label} ({cdna_change} OR {protein_change}) {disease_label}"
                else:
                    pubmed_query = f"{gene_label} {cdna_change} {disease_label}"
            else:
                pubmed_query = f"{gene_label} {cdna_change} {disease_label}"
            result = search_pubmed(pubmed_query)
            # print(f"DEBUG - pubmed query: '{pubmed_query}' | total_found: {result.get('total_found', 'error')}")
            return result, pubmed_query
        elif criterion in ("PP5", "BP6"):
            # PP5/BP6 require exact variant classification from ClinVar,
            # not a codon-position search — use the dedicated exact-variant lookup.
            return search_clinvar_for_exact_variant(input_value), input_value
        else:
            return search_clinvar(input_value), input_value

    elif tool == "gnomad":
        if input_value.startswith("NM_") or "c." in input_value or "p." in input_value:
            converted = hgvs_to_gnomad_format(input_value)
            if isinstance(converted, dict) and "error" in converted:
                return converted, input_value
            input_value = converted
        gnomad_result = query_gnomad(input_value)
        gnomad_result = _annotate_gnomad_frequency(gnomad_result)
        return gnomad_result, input_value

    elif tool == "gnomad_gene":
        # Gene-level constraint query for PP2 (missense Z-score) and BP1 (pLI, LOEUF)
        if not gene:
            return {"error": "Gene symbol required for gene-level constraint query — add this gene to GENE_DB in planrag.py"}, input_value
        gene_result = query_gnomad_gene_constraint(gene)
        gene_result = _annotate_gnomad_gene_constraint(gene_result)
        # print(f"DEBUG - gnomad_gene: {gene} | mis_z={gene_result.get('mis_z')} | pLI={gene_result.get('pLI')} | LOEUF={gene_result.get('oe_lof_upper')}")
        return gene_result, gene

    elif tool == "revel_spliceai":
        if input_value.startswith("NM_") or "c." in input_value or "p." in input_value:
            converted = hgvs_to_gnomad_format(input_value)
            if isinstance(converted, dict) and "error" in converted:
                return converted, input_value
            input_value = converted
        revel_result = query_revel_spliceai(input_value)
        revel_result = _annotate_spliceai(revel_result)
        # print(f"DEBUG - revel_spliceai: REVEL={revel_result.get('revel_score')} | "
        #       f"DS_AG={revel_result.get('DS_AG')} DS_AL={revel_result.get('DS_AL')} "
        #       f"DS_DG={revel_result.get('DS_DG')} DS_DL={revel_result.get('DS_DL')}")
        return revel_result, input_value

    elif tool == "spliceai":
        spliceai_result = query_spliceai(input_value)
        spliceai_result = _annotate_spliceai(spliceai_result)
        return spliceai_result, input_value

    elif tool == "erepo":
        if not gene:
            return {"error": "Gene symbol could not be determined for ERepo lookup — add this gene to GENE_DB in planrag.py"}, input_value
        gene_label = gene
        vep_result = annotate_variant(input_value)
        if "error" in vep_result:
            return vep_result, input_value
        codon_position = vep_result.get("codon_position")
        if codon_position is None:
            return {"error": "VEP did not return a protein position — cannot search ERepo"}, input_value
        result = search_erepo_by_position(gene_label, codon_position)
        # Remove the query variant itself from results — PS1/PM5 require other variants
        # at the same position. Match on the cdna change (e.g. "c.557G>T").
        query_cdna = input_value.split(":")[-1] if ":" in input_value else None
        if query_cdna and "classifications" in result:
            before = len(result["classifications"])
            result["classifications"] = [
                c for c in result["classifications"]
                if query_cdna not in c.get("hgvs", "")
            ]
            after = len(result["classifications"])
            # print(f"DEBUG - erepo query: {gene_label} position {codon_position} | classifications found: {after} (filtered {before - after} self-match)")
        else:
            # print(f"DEBUG - erepo query: {gene_label} position {codon_position} | classifications found: {len(result.get('classifications', []))}")
            # pass
            return {"error": "Erepo did not return valid reponse, no classifications found"}, input_value

        # # ClinVar fallback — if ERepo has no other variants at this codon,
        # # search ClinVar for HHT VCEP-classified LP/P variants at the same position.
        # if not result.get("classifications"):
        #     ref_aa = vep_result.get("amino_acid_ref")
        #     if ref_aa:
        #         # print(f"DEBUG - erepo: 0 results, falling back to ClinVar for {ref_aa}{codon_position}")
        #         clinvar_result = search_clinvar_for_codon(
        #             gene_label, codon_position, ref_aa, query_cdna
        #         )
        #         if "error" not in clinvar_result:
        #             # print(f"DEBUG - clinvar fallback: {len(clinvar_result.get('classifications', []))} LP/P variants found at codon {codon_position}")
        #             result = clinvar_result
        #         else:
        #             # print(f"DEBUG - clinvar fallback error: {clinvar_result['error']}")
        #             pass

        # Split results by alt amino acid — PS1 needs same AA, PM5 needs different AA.
        # Done here deterministically so the LLM never has to reason about it.
        _alt_re = re.compile(r'p\.[A-Za-z]{3}\d+([A-Za-z]{3})')
        alt_aa = vep_result.get("amino_acid_alt", "").lower()
        if alt_aa and "classifications" in result:
            same_aa, diff_aa = [], []
            for c in result["classifications"]:
                m = _alt_re.match(c.get("protein_change", ""))
                if m and m.group(1).lower() == alt_aa:
                    same_aa.append(c)
                else:
                    diff_aa.append(c)
            result["same_aa_classifications"] = same_aa
            result["different_aa_classifications"] = diff_aa

        return result, f"{gene_label} position {codon_position}"

    elif tool == "pubmed":
        # Generic PubMed search — PS4 now routes through the clinvar branch instead
        disease_label = disease or "HHT"
        gene_label = gene or disease_label
        cdna_change = input_value.split(":")[-1] if ":" in input_value else input_value
        vep_result = annotate_variant(input_value)
        if "error" not in vep_result:
            protein_change   = vep_result.get("protein_change")
            protein_change_1 = vep_result.get("protein_change_1letter")
            if protein_change and protein_change_1:
                pubmed_query = f"{gene_label} ({cdna_change} OR {protein_change} OR {protein_change_1}) {disease_label}"
            elif protein_change:
                pubmed_query = f"{gene_label} ({cdna_change} OR {protein_change}) {disease_label}"
            else:
                pubmed_query = f"{gene_label} {cdna_change} {disease_label}"
        else:
            pubmed_query = f"{gene_label} {cdna_change} {disease_label}"
        result = search_pubmed(pubmed_query)
        return result, pubmed_query

    elif tool == "vep":
        vep_result = annotate_variant(input_value)
        if "error" in vep_result:
            return vep_result, input_value
        codon_position = vep_result.get("codon_position")

        # Inject lof_mechanism from GENE_DB so the LLM can gate PVS1 correctly.
        # Without this, the LLM conservatively says "LOF not established" for any
        # gene not hardcoded in its training data.
        if gene and gene in GENE_DB:
            vep_result["lof_mechanism"] = GENE_DB[gene].get("lof_mechanism")
            vep_result["lof_mechanism_note"] = GENE_DB[gene].get("lof_mechanism_note")
        else:
            vep_result["lof_mechanism"] = None
            vep_result["lof_mechanism_note"] = "Gene not in GENE_DB — LOF mechanism unknown; PVS1 requires manual review."

        # Prefer critical_regions from the planrag entry (HHT VCEP gene-specific regions).
        # Fall back to GENE_DB pm1_critical_regions when the rag entry has none —
        # this covers ACMG mode for genes like LDLR where domain boundaries are known
        # but the generic ACMG_PLANRAG_DB PM1 entry is gene-agnostic.
        critical_regions = (rag_entry or {}).get("critical_regions")
        if critical_regions is None and gene and gene in GENE_DB:
            gene_regions = GENE_DB[gene].get("pm1_critical_regions")
            if gene_regions:
                # check_pm1_critical_region expects {"ranges": [...], "discrete": [...]}
                # GENE_DB stores a flat list of range dicts — wrap it into that shape.
                critical_regions = {"ranges": gene_regions, "discrete": []}
                # print(f"DEBUG - vep/PM1: using GENE_DB critical regions for {gene} "
                #       f"({len(gene_regions)} region(s))")

        if codon_position is not None and critical_regions is not None:
            pm1_check = check_pm1_critical_region(codon_position, critical_regions)
            vep_result["in_critical_region"] = pm1_check["in_critical_region"]
            vep_result["pm1_region_name"] = pm1_check["region_name"]
        return vep_result, input_value
    
    elif tool == "functional_evidence":
        from tools.functional_evidence import analyze_variant
        result = analyze_variant(variant=variant)
        if "error" in result:
            return {
                "error": f"Functional evidence analysis failed: {result.get('error', 'unknown error')}"
            }, input_value
        return result, input_value
        
    else:
        return {"error": f"Unknown tool: {tool}"}, input_value


def interpret_evidence(
    criterion: str,
    variant: str,
    disease: str,
    tool_used: str,
    tool_input: str,
    evidence: dict,
    rag_entry: dict | None = None,
    feedback: str | None = None,
    variant_type: str | None = None
) -> dict:
    """
    Asks the LLM to interpret tool output and map it to the ACMG criterion.
    tool_input is the exact string passed to the API — set by code, not inferred by the LLM.
    rag_entry is injected as ground-truth rules so the LLM applies the correct thresholds.
    If feedback is provided (retry path), it is injected so the LLM knows
    exactly what it got wrong in the previous attempt.
    """
    rag_context = ""
    if rag_entry:
        rag_context = f"""
Classification rules for {criterion} (use these as ground truth):
- Threshold: {rag_entry.get('threshold', 'N/A')}
- Instructions: {rag_entry.get('instructions', 'N/A')}

Apply these rules exactly when setting the applies field.
"""

    feedback_block = ""
    if feedback:
        feedback_block = f"""
A previous interpretation of this evidence was rejected with the following feedback:
{feedback}

Correct this specific error in your response.
"""

    # applied_strength guidance — variable-strength criteria must set this explicitly.
    # Fixed-strength criteria are enforced in code below, so we tell the LLM to omit them.
    # BS1 is benign but has two strength levels (benign_strong / benign_supporting).
    variable_strength_criteria = {"PVS1", "PS3", "PS4", "PM5", "PP1"}
    variable_benign_strength_criteria = {"BS1"}
    if criterion in variable_strength_criteria:
        strength_note = (
            '\n"applied_strength": "<very_strong | strong | moderate | supporting>  '
            '← set based on the strength level that applies per the instructions above",'
        )
    elif criterion in variable_benign_strength_criteria:
        strength_note = (
            '\n"applied_strength": "<benign_strong | benign_supporting>  '
            '← set to benign_strong (FAF >0.2-<1% or Supporting+2hom) or benign_supporting (FAF >0.08-0.2%)",'
        )
    else:
        strength_note = '\n"applied_strength": null,  ← will be set automatically, leave null'

    variant_type_line = f"\nVariant type: {variant_type}" if variant_type else ""

    prompt = f"""You are a variant classification assistant applying ACMG criteria.

Variant: {variant}{variant_type_line}
Disease: {disease}
Criterion: {criterion}
Tool used: {tool_used}
Evidence retrieved:
{json.dumps(evidence, indent=2)}
{rag_context}{feedback_block}
Based on this evidence, determine whether criterion {criterion} applies.

Use the provided output schema.

Important rules:
- The evidence field should be a concise summary of the raw evidence.
- The reasoning field should explain how the evidence maps to criterion {criterion}.
- The applies field must reflect whether the criterion applies.
- Use status="complete" if the interpretation succeeds.
- Use status="error" only if the task cannot be completed.

{strength_note}
"""
    result = {
        "criterion": criterion,
    }
    result.update(call_task_agent(prompt, TaskInterpretation).model_dump())
    # raw = call_ollama(prompt)
    # result = parse_json_response(raw)

    # enforce tool_used, tool_input, criterion, disease — never trust the LLM to set these correctly
    result["tool_used"] = tool_used
    result["tool_input"] = tool_input
    result["disease"] = disease

    # enforce applied_strength for fixed-strength criteria
    # variable-strength criteria (PVS1, PS3, PS4, PM5, PP1) set their own applied_strength
    # BS1 is benign variable-strength — two levels (benign_strong / benign_supporting)
    _FIXED_STRENGTH: dict[str, str] = {
        # ── HHT VCEP criterion names ───────────────────────────────────────────
        "PM2_SUPPORTING": "supporting",
        "PP4_MODERATE":   "moderate",
        "BS3_SUPPORTING": "benign_supporting",
        # ── Shared (same name in both HHT VCEP and ACMG) ──────────────────────
        "PP3":  "supporting",
        "PM1":  "moderate",
        "PM4":  "moderate",
        "PS1":  "strong",
        "PS2":  "strong",
        "BA1":  "benign_stand_alone",
        # BS1 is intentionally absent from both — treated as variable benign strength below
        "BS4":  "benign_strong",
        "BP2":  "benign_supporting",
        "BP4":  "benign_supporting",
        "BP5":  "benign_supporting",
        "BP7":  "benign_supporting",
        # ── ACMG-only criterion names (standard ACMG strength) ─────────────────
        "PM2":  "moderate",    # Moderate in ACMG (Supporting in some VCEP specs)
        "BS2":  "benign_strong",
        "BS3":  "benign_strong",
        "BP3":  "benign_supporting",
        "BP6":  "benign_supporting",
        "PP5":  "supporting",
        "PP2":  "supporting",
        "BP1":  "benign_supporting",
    }
    if not result.get("applies"):
        # Criterion does not apply — applied_strength must be null.
        # Scoring only counts applied criteria, so this value is irrelevant,
        # but the judge agent flags non-null applied_strength on non-applied criteria.
        result["applied_strength"] = None
    else:
        fixed = _FIXED_STRENGTH.get(criterion)
        if fixed:
            result["applied_strength"] = fixed
        elif criterion in variable_benign_strength_criteria:
            # BS1: validate LLM chose a valid benign strength; default to benign_strong
            if result.get("applied_strength") not in ("benign_strong", "benign_supporting"):
                result["applied_strength"] = "benign_strong"
        elif "applied_strength" not in result or result.get("applied_strength") is None:
            # variable-strength criterion but LLM didn't set it — default to criterion's base strength
            base = (rag_entry or {}).get("strength")
            result["applied_strength"] = base

    return result


def run_task(task: dict, tool_results: ToolResults | None, gene_symbol: str | None, feedback: str | None = None) -> tuple[dict, dict]:
    """
    Main entry point called by pipeline.py and by Debug/Judge agents on retry.

    First attempt: tool is taken directly from task["tool"] set by the Plan agent.
    No LLM call for tool selection — the plan already decided this.

    Retry (feedback is not None): LLM re-selects the tool using the feedback,
    and interpret_evidence() receives the feedback so it knows what to correct.

    rag_entry is queried once per task and passed into interpret_evidence() as
    ground-truth rules, so the LLM applies the correct thresholds on the first attempt.
    """
    criterion = task["criterion"]
    variant = task["variant"]
    disease = task["disease"]
    tool_cache_update = {}

    # Detect gene from transcript (NM_... prefix) so gene-specific planrag branches
    # and tool queries (erepo, PubMed) use the correct gene symbol.
    gene = None
    if variant.startswith("NM_") and ":" in variant:
        gene = get_gene_from_transcript(variant.split(":")[0])
    if gene is None and gene_symbol:
        # Fall back to the VEP-resolved gene symbol (passed in as a parameter) when the
        # transcript isn't mapped in GENE_DB. Previously this checked task.get("gene_symbol"),
        # which the plan agent doesn't set — so ERepo (PS1/PM5) always errored for
        # ACVRL1/ENG even though the gene was known.
        gene = gene_symbol

    rag_entry = query(criterion, gene=gene, disease=disease)
    if rag_entry is None:
        _task_warning(f"No PlanRAG entry for {criterion}; proceeding without rules context.")

    if feedback:
        # retry path — LLM re-selects tool with correction context
        tool_decision = select_tool(criterion, variant, disease=disease, feedback=feedback)
    else:
        # first attempt — trust the plan, no LLM call
        tool_decision = {"tool": task["tool"], "reason": "specified by Plan agent"}

    # check tool selection itself didn't fail
    if "error" in tool_decision or "tool" not in tool_decision:
        error_msg = tool_decision.get("error") or tool_decision.get("feedback", "Tool selection returned invalid response")
        return {
            "criterion": criterion,
            "evidence": None,
            "reasoning": None,
            "applies": None,
            "tool_used": None,
            "tool_input": None,
            "disease": disease,
            "status": "error",
            "error": tool_decision["error"],
        }, tool_cache_update
    
    selected_tool = tool_decision["tool"]
    cached_result = tool_results.get(selected_tool) if tool_results else None

    if cached_result and "error" not in cached_result.get("evidence", {}):
        evidence = cached_result["evidence"]
        actual_input = cached_result["actual_input"]
    else: 
        evidence, actual_input = run_tool(tool_decision, variant, rag_entry=rag_entry, gene=gene, disease=disease)
        tool_cache_update[selected_tool] = {"evidence": evidence, "actual_input" : actual_input}

    if "error" in evidence:
        return {
            "criterion": criterion,
            "evidence": None,
            "reasoning": None,
            "applies": None,
            "tool_used": tool_decision["tool"],
            "tool_input": actual_input,
            "disease": disease,
            "status": "error",
            "error": evidence["error"],
        }, tool_cache_update

    return interpret_evidence(
        criterion, variant, disease,
        tool_decision["tool"], actual_input, evidence,
        rag_entry=rag_entry,
        feedback=feedback,
        variant_type=task.get("variant_type"),
    ), tool_cache_update
