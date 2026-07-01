import requests
from urllib.parse import quote
from tools.utils import hgvs_to_gnomad_format

MYVARIANT_URL = "https://myvariant.info/v1"
ENSEMBL_URL = "https://rest.ensembl.org"


def _gnomad_to_myvariant_id(gnomad: str) -> str:
    """
    Converts gnomAD format (12-51914005-G-T) to MyVariant.info genomic HGVS (chr12:g.51914005G>T).
    Pure string conversion — no API call.
    """
    chrom, pos, ref, alt = gnomad.split("-")
    return f"chr{chrom}:g.{pos}{ref}>{alt}"


def _to_gnomad_format(variant: str) -> str | dict:
    """
    Ensures variant is in gnomAD format (chrom-pos-ref-alt).
    Converts HGVS if needed. Returns error dict on failure.
    """
    if variant.startswith("NM_") or "c." in variant or "p." in variant:
        result = hgvs_to_gnomad_format(variant)
        if isinstance(result, dict) and "error" in result:
            return result
        return result
    return variant


def query_revel(gnomad_variant: str) -> dict:
    """
    Fetches REVEL score for a variant via MyVariant.info /variant/{id} endpoint.
    Input: gnomAD format (chrom-pos-ref-alt), GRCh38 coordinates.
    Returns: {"revel_score": float} or {"revel_score": None} if not available.

    Critical: must pass assembly=hg38 — MyVariant.info defaults to hg19.
    Coordinates from Ensembl Variant Recoder are GRCh38.
    """
    myvariant_id = _gnomad_to_myvariant_id(gnomad_variant)
    from urllib.parse import quote as urlquote
    encoded_id = urlquote(myvariant_id, safe="")

    try:
        response = requests.get(
            f"{MYVARIANT_URL}/variant/{encoded_id}",
            params={
                "fields": "dbnsfp.revel.score",
                "assembly": "hg38",       # REQUIRED — default is hg19
            },
            headers={"Accept": "application/json"},
            timeout=10
        )
    except requests.exceptions.RequestException as e:
        return {"error": f"MyVariant.info request failed: {e}"}

    if response.status_code == 404:
        return {
            "revel_score": None,
            "note": "Variant not found in MyVariant.info (hg38) — REVEL score unavailable"
        }

    if response.status_code != 200:
        return {"error": f"MyVariant.info returned {response.status_code}: {response.text}"}

    data = response.json()

    try:
        score = data["dbnsfp"]["revel"]["score"]
        # score can be a list when multiple transcripts exist — take the max
        if isinstance(score, list):
            score = max(score)
        return {"revel_score": float(score)}
    except (KeyError, TypeError):
        return {
            "revel_score": None,
            "note": "REVEL score field not present in MyVariant.info response"
        }


def query_spliceai(variant: str) -> dict:
    """
    Fetches SpliceAI delta scores via Ensembl VEP REST API.
    Accepts HGVS (preferred) or gnomAD format — handles both.
    Returns: {"DS_AG": float, "DS_AL": float, "DS_DG": float, "DS_DL": float} or {"error": str}.

    VEP region endpoint format for SNV: CHROM:POS-POS:1/ALT (1-based, START==END).
    """
    is_hgvs = variant.startswith("NM_") or "c." in variant or "p." in variant

    if is_hgvs:
        encoded = quote(variant, safe="")
        url = f"{ENSEMBL_URL}/vep/human/hgvs/{encoded}"
    else:
        # gnomAD format: 12-51914005-G-T
        # VEP region format: CHROM:START-END:STRAND/ALT (1-based, START==END for SNV)
        parts = variant.split("-")
        if len(parts) != 4:
            return {"error": f"Unrecognised variant format for SpliceAI lookup: {variant}"}
        chrom, pos, ref, alt = parts
        region = f"{chrom}:{pos}-{pos}:1/{alt}"
        encoded = quote(region, safe=":/-")
        url = f"{ENSEMBL_URL}/vep/human/region/{encoded}"

    try:
        response = requests.get(
            url,
            params={"SpliceAI": 1},
            headers={"Content-Type": "application/json"},
            timeout=15
        )
    except requests.exceptions.RequestException as e:
        return {"error": f"Ensembl VEP request failed: {e}"}

    if response.status_code != 200:
        return {"error": f"Ensembl VEP returned {response.status_code}: {response.text}"}

    data = response.json()

    if not data or not isinstance(data, list):
        return {"error": "Ensembl VEP returned empty or unexpected response"}

    # collect SpliceAI scores across all transcript consequences
    # take max per direction — most damaging prediction across transcripts
    ds_ag, ds_al, ds_dg, ds_dl = [], [], [], []

    for hit in data:
        for tc in hit.get("transcript_consequences", []):
            spliceai = tc.get("spliceai")
            if not spliceai:
                continue
            if spliceai.get("DS_AG") is not None:
                ds_ag.append(float(spliceai["DS_AG"]))
            if spliceai.get("DS_AL") is not None:
                ds_al.append(float(spliceai["DS_AL"]))
            if spliceai.get("DS_DG") is not None:
                ds_dg.append(float(spliceai["DS_DG"]))
            if spliceai.get("DS_DL") is not None:
                ds_dl.append(float(spliceai["DS_DL"]))

    if not any([ds_ag, ds_al, ds_dg, ds_dl]):
        return {
            "DS_AG": None,
            "DS_AL": None,
            "DS_DG": None,
            "DS_DL": None,
            "note": "SpliceAI scores not available for this variant in Ensembl VEP"
        }

    return {
        "DS_AG": max(ds_ag) if ds_ag else None,
        "DS_AL": max(ds_al) if ds_al else None,
        "DS_DG": max(ds_dg) if ds_dg else None,
        "DS_DL": max(ds_dl) if ds_dl else None,
    }


def query_revel_spliceai(variant: str) -> dict:
    """
    Main entry point for PP3 and BP4 — fetches both REVEL and SpliceAI.
    Input: HGVS or gnomAD format.
    Returns combined dict with revel_score and all four SpliceAI delta scores.
    """
    gnomad = _to_gnomad_format(variant)
    if isinstance(gnomad, dict) and "error" in gnomad:
        return gnomad

    revel = query_revel(gnomad)
    spliceai = query_spliceai(variant)

    result = {}

    if "error" in revel:
        result["revel_score"] = None
        result["revel_error"] = revel["error"]
    else:
        result["revel_score"] = revel.get("revel_score")
        if "note" in revel:
            result["revel_note"] = revel["note"]

    if "error" in spliceai:
        result["DS_AG"] = None
        result["DS_AL"] = None
        result["DS_DG"] = None
        result["DS_DL"] = None
        result["spliceai_error"] = spliceai["error"]
    else:
        result["DS_AG"] = spliceai.get("DS_AG")
        result["DS_AL"] = spliceai.get("DS_AL")
        result["DS_DG"] = spliceai.get("DS_DG")
        result["DS_DL"] = spliceai.get("DS_DL")
        if "note" in spliceai:
            result["spliceai_note"] = spliceai["note"]

    # only hard-fail if both APIs completely errored
    if "revel_error" in result and "spliceai_error" in result:
        return {
            "error": (
                f"Both REVEL and SpliceAI lookups failed. "
                f"REVEL: {result['revel_error']}. "
                f"SpliceAI: {result['spliceai_error']}"
            )
        }

    return result


# -----------------------------------------------------------------------------
# MANUAL TEST
# python3.12 -m tools.computational
# Expected for NM_000020.3:c.557G>T (ACVRL1 missense, GRCh38 12-51914005-G-T):
#   revel_score: a float (e.g. ~0.5-0.9 range for missense)
#   DS_AG/AL/DG/DL: four floats (confirmed working: 0.0, 0.01, 0.0, 0.0)
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    import json
    TEST_HGVS = "NM_000020.3:c.557G>T"
    TEST_GNOMAD = "12-51914005-G-T"



