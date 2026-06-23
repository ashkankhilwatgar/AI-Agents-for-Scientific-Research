import requests
from urllib.parse import quote
import json
import time

ENSEMBL_URL = "https://rest.ensembl.org"
NCBI_VARIATION_URL = "https://api.ncbi.nlm.nih.gov/variation/v0"
MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds between retries

_RECODER_CACHE: dict[str, str] = {}

# Maps NC_ accession prefix to chromosome name (GRCh38)
_NC_TO_CHROM = {f"NC_{str(i).zfill(6)}": str(i) for i in range(1, 23)}
_NC_TO_CHROM["NC_000023"] = "X"
_NC_TO_CHROM["NC_000024"] = "Y"
_NC_TO_CHROM["NC_012920"] = "MT"

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


def get_variant_type(variant: str) -> dict:
    """
    Calls Ensembl VEP to determine variant consequence type.
    Accepts HGVS (NM_... format) or gnomAD format (chrom-pos-ref-alt).

    Returns:
        {
            "variant_type": "<missense | synonymous | intronic | splice_site |
                             splice_region | nonsense | frameshift |
                             inframe_insertion | inframe_deletion |
                             stop_lost | start_lost | utr | other>",
            "raw_consequence": "<VEP most_severe_consequence string>"
        }
    or {"error": "<message>"} on failure.
    """
    is_hgvs = variant.startswith("NM_") or "c." in variant or "p." in variant

    if is_hgvs:
        encoded = quote(variant, safe="")
        url = f"{ENSEMBL_URL}/vep/human/hgvs/{encoded}"
        params = {}
    else:
        # gnomAD format: chrom-pos-ref-alt → VEP region: CHROM:POS-POS:1/ALT
        parts = variant.split("-")
        if len(parts) != 4:
            return {"error": f"Unrecognised variant format for VEP lookup: {variant}"}
        chrom, pos, ref, alt = parts
        region = f"{chrom}:{pos}-{pos}:1/{alt}"
        encoded = quote(region, safe=":/-")
        url = f"{ENSEMBL_URL}/vep/human/region/{encoded}"
        params = {}

    last_error = "No attempts completed"

    for attempt in range(MAX_RETRIES):
        try:
            response = requests.get(
                url,
                params=params,
                headers={"Content-Type": "application/json"},
                timeout=15
            )
        except requests.exceptions.RequestException as e:
            last_error = str(e)
            time.sleep(RETRY_DELAY)
            continue

        if response.status_code in (429, 500, 503):
            last_error = f"HTTP {response.status_code}"
            time.sleep(RETRY_DELAY * (attempt + 1))
            continue

        if response.status_code != 200:
            return {"error": f"Ensembl VEP returned {response.status_code}: {response.text}"}

        data = response.json()

        if not data or not isinstance(data, list):
            return {"error": "Ensembl VEP returned empty or unexpected response"}

        raw_consequence = data[0].get("most_severe_consequence", "")

        if not raw_consequence:
            return {"error": "VEP response missing most_severe_consequence field"}

        return {
            "variant_type": CONSEQUENCE_MAP.get(raw_consequence, "other"),
            "raw_consequence": raw_consequence,
        }

    return {"error": f"Ensembl VEP failed after {MAX_RETRIES} retries: {last_error}"}

def hgvs_to_gnomad_format(hgvs: str) -> str:
    """
    Converts HGVS to gnomAD format (chrom-pos-ref-alt) using NCBI Variation Services.

    Two-step process:
      1. hgvs/{hgvs}/contextuals  → SPDI with NM_ seq_id (0-based)
      2. spdi/{spdi}/canonical_representative → SPDI with NC_ seq_id (GRCh38, 0-based)

    Returns gnomAD format: "{chrom}-{pos}-{ref}-{alt}" (1-based VCF position).
    """
    if hgvs in _RECODER_CACHE:
        return _RECODER_CACHE[hgvs]

    encoded = quote(hgvs, safe="")
    last_error = "No attempts completed"

    # --- Step 1: HGVS → SPDI (NM_ coordinates) ---
    spdi = None
    for attempt in range(MAX_RETRIES):
        try:
            r = requests.get(
                f"{NCBI_VARIATION_URL}/hgvs/{encoded}/contextuals",
                headers={"Accept": "application/json"},
                timeout=15
            )
            if r.status_code in (429, 500, 503):
                last_error = f"HTTP {r.status_code}"
                time.sleep(RETRY_DELAY * (attempt + 1))
                continue
            if r.status_code != 200:
                return {"error": f"NCBI contextuals failed for {hgvs}: HTTP {r.status_code}"}
            spdis = r.json().get("data", {}).get("spdis", [])
            if not spdis:
                return {"error": f"NCBI contextuals returned no SPDIs for {hgvs}"}
            spdi = spdis[0]
            break
        except requests.RequestException as e:
            last_error = str(e)
            time.sleep(RETRY_DELAY)
            continue

    if spdi is None:
        return {"error": f"NCBI contextuals failed after {MAX_RETRIES} retries: {last_error}"}

    # --- Step 2: SPDI (NM_) → canonical genomic SPDI (NC_) ---
    spdi_str = f"{spdi['seq_id']}:{spdi['position']}:{spdi['deleted_sequence']}:{spdi['inserted_sequence']}"
    genomic_spdi = None

    for attempt in range(MAX_RETRIES):
        try:
            r = requests.get(
                f"{NCBI_VARIATION_URL}/spdi/{quote(spdi_str, safe='')}/canonical_representative",
                headers={"Accept": "application/json"},
                timeout=15
            )
            if r.status_code in (429, 500, 503):
                last_error = f"HTTP {r.status_code}"
                time.sleep(RETRY_DELAY * (attempt + 1))
                continue
            if r.status_code != 200:
                return {"error": f"NCBI canonical_representative failed: HTTP {r.status_code}"}
            genomic_spdi = r.json().get("data", {})
            break
        except requests.RequestException as e:
            last_error = str(e)
            time.sleep(RETRY_DELAY)
            continue

    if genomic_spdi is None:
        return {"error": f"NCBI canonical_representative failed after {MAX_RETRIES} retries: {last_error}"}

    # --- Step 3: NC_ accession → chromosome name, 0-based → 1-based ---
    nc_accession = genomic_spdi.get("seq_id", "")
    nc_prefix = nc_accession.split(".")[0]  # e.g. "NC_000012"
    chrom = _NC_TO_CHROM.get(nc_prefix)
    if chrom is None:
        return {"error": f"Unrecognised NC_ accession: {nc_accession}"}

    pos = genomic_spdi["position"] + 1  # 0-based → 1-based VCF
    ref = genomic_spdi["deleted_sequence"]
    alt = genomic_spdi["inserted_sequence"]

    result = f"{chrom}-{pos}-{ref}-{alt}"
    _RECODER_CACHE[hgvs] = result
    return result


def extract_json_from_response(raw: str) -> str:
    """
    Handles deepseek-r1 thinking blocks.
    Tries content after </think> first, falls back to content inside <think> if empty.
    """
    if "<think>" in raw and "</think>" in raw:
        after_think = raw.split("</think>")[-1].strip()
        if after_think:
            return after_think
        # JSON may be inside the think block — extract it
        inside_think = raw.split("<think>")[-1].split("</think>")[0].strip()
        return inside_think
    return raw.strip()


def parse_json_response(raw: str) -> dict:
    text = extract_json_from_response(raw)

    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    text = text.strip()

    if not text:
        return {
            "pass": False,
            "error_type": "reasoning",
            "feedback": "Judge agent received empty response from model"
        }

    # extract just the JSON object, ignoring any text before or after
    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end == 0:
        return {
            "pass": False,
            "error_type": "reasoning",
            "feedback": "Judge agent could not find JSON object in model response"
        }

    return json.loads(text[start:end])