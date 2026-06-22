import requests
from urllib.parse import quote

ENSEMBL_URL = "https://rest.ensembl.org"
MAX_RETRIES = 3

# Maps VEP most_severe_consequence to simplified variant type categories
# used by the pipeline for criterion pre-filtering.
CONSEQUENCE_MAP = {
    "missense_variant":        "missense",
    "synonymous_variant":      "synonymous",
    "intron_variant":          "intronic",
    "splice_donor_variant":    "splice_site",
    "splice_acceptor_variant": "splice_site",
    "splice_region_variant":   "splice_region",
    "stop_gained":             "nonsense",
    "frameshift_variant":      "frameshift",
    "inframe_insertion":       "inframe_insertion",
    "inframe_deletion":        "inframe_deletion",
    "stop_lost":               "stop_lost",
    "start_lost":              "start_lost",
    "5_prime_UTR_variant":     "utr",
    "3_prime_UTR_variant":     "utr",
}


def _check_repeat_region(data: list) -> bool:
    """
    Checks whether the variant overlaps a repeat region using the Ensembl overlap API.
    Returns True if a repeat is found, False if not.
    Raises RuntimeError on API failure after all retries.
    """
    first_hit = data[0] if data and isinstance(data, list) else {}

    chrom = first_hit.get("seq_region_name")
    start = first_hit.get("start")
    end = first_hit.get("end")

    if not chrom or not start or not end:
        raise RuntimeError("Missing coordinates for repeat-region check")

    ext = f"/overlap/region/human/{chrom}:{start}-{end}?feature=repeat"
    last_error = "No attempts completed"

    for _ in range(MAX_RETRIES):
        try:
            r = requests.get(
                ENSEMBL_URL + ext,
                headers={"Content-Type": "application/json"},
                timeout=15
            )

            if r.status_code != 200:
                last_error = f"{r.status_code}: {r.text}"
                continue

            repeat_hits = r.json()

            if not isinstance(repeat_hits, list):
                raise RuntimeError("Unexpected API response format from repeat-region endpoint")

            return len(repeat_hits) > 0

        except requests.RequestException as e:
            last_error = str(e)
            continue

    raise RuntimeError(f"Repeat-region API failed after {MAX_RETRIES} retries: {last_error}")


def annotate_variant(variant: str) -> dict:
    """
    Calls Ensembl VEP to annotate a variant for use by PVS1 and PM4.

    Accepts HGVS (NM_... format) or gnomAD format (chrom-pos-ref-alt).

    Returns a dict with:
        - variant_consequence: VEP consequence term (e.g. "missense_variant")
        - codon_position: protein position (int), or None if non-coding
        - overlaps_repeat_region: bool (only present for inframe indels)
        - repeat_region_note: str (only present if repeat check failed gracefully)

    Returns {"error": "..."} on unrecoverable failure — never raises.
    """
    is_hgvs = variant.startswith("NM_") or "c." in variant or "p." in variant

    if is_hgvs:
        encoded = quote(variant, safe="")
        url = f"{ENSEMBL_URL}/vep/human/hgvs/{encoded}"
    else:
        parts = variant.split("-")
        if len(parts) != 4:
            return {"error": f"Unrecognised variant format for VEP lookup: {variant}"}
        chrom, pos, ref, alt = parts
        region = f"{chrom}:{pos}-{pos}:1/{alt}"
        encoded = quote(region, safe=":/-")
        url = f"{ENSEMBL_URL}/vep/human/region/{encoded}"

    last_error = "No attempts completed"

    for _ in range(MAX_RETRIES):
        try:
            response = requests.get(
                url,
                headers={"Content-Type": "application/json"},
                timeout=15,
                params={"refseq": 1}
            )

            if response.status_code != 200:
                last_error = f"{response.status_code}: {response.text}"
                continue

            data = response.json()

            if not data or not isinstance(data, list):
                last_error = "VEP returned empty or non-list response"
                continue

            transcript_consequences = data[0].get("transcript_consequences")
            if not transcript_consequences:
                last_error = "VEP response missing transcript_consequences"
                continue

            tc = transcript_consequences[0]
            consequence_terms = tc.get("consequence_terms")
            if not consequence_terms:
                last_error = "VEP transcript_consequences missing consequence_terms"
                continue

            result = {
                "variant_consequence": consequence_terms[0],
                "codon_position": tc.get("protein_start"),  # None for non-coding
            }

            # repeat region check — only for in-frame indels (required for PM4)
            indel_consequences = {"inframe_deletion", "inframe_insertion"}
            if result["variant_consequence"] in indel_consequences:
                try:
                    result["overlaps_repeat_region"] = _check_repeat_region(data)
                except RuntimeError as e:
                    # degrade gracefully — PM4 LLM reasoning will note the gap
                    result["overlaps_repeat_region"] = None
                    result["repeat_region_note"] = f"Repeat region check failed: {e}"

            return result

        except requests.RequestException as e:
            last_error = str(e)
            continue

    return {"error": f"Variant annotation API failed after {MAX_RETRIES} retries: {last_error}"}


def check_pm1_critical_region(codon_position: int, critical_regions: dict) -> dict:
    """
    Deterministic check: is the given protein position within any PM1
    critical region defined in the RAG entry for this gene?

    critical_regions is the 'critical_regions' field from the planrag entry:
        {
            "ranges":   [{"start": int, "end": int, "name": str}, ...],
            "discrete": [{"positions": [int, ...], "name": str}, ...]
        }

    Returns:
        {
            "in_critical_region": bool,
            "region_name": str | None
        }
    """
    for region in critical_regions.get("ranges", []):
        if region["start"] <= codon_position <= region["end"]:
            return {
                "in_critical_region": True,
                "region_name": region["name"],
            }

    for region in critical_regions.get("discrete", []):
        if codon_position in region["positions"]:
            return {
                "in_critical_region": True,
                "region_name": f"{region['name']} (position {codon_position})",
            }

    return {
        "in_critical_region": False,
        "region_name": None,
    }