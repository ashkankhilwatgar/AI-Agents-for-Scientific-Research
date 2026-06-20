import requests
from urllib.parse import quote
import json

ENSEMBL_URL = "https://rest.ensembl.org"

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

    try:
        response = requests.get(
            url,
            params=params,
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

    raw_consequence = data[0].get("most_severe_consequence", "")

    if not raw_consequence:
        return {"error": "VEP response missing most_severe_consequence field"}

    variant_type = CONSEQUENCE_MAP.get(raw_consequence, "other")

    return {
        "variant_type": variant_type,
        "raw_consequence": raw_consequence,
    }

def hgvs_to_gnomad_format(hgvs: str) -> str:
    """
    Converts HGVS to gnomAD format (chrom-pos-ref-alt) using Ensembl Variant Recoder.
    Returns GRCh38 coordinates only, filtering out LRG entries.
    """
    encoded = quote(hgvs, safe="")
    url = f"{ENSEMBL_URL}/variant_recoder/human/{encoded}"

    headers = {"Content-Type": "application/json"}
    params = {"vcf_string": 1}

    response = requests.get(url, headers=headers, params=params)

    if response.status_code != 200:
        return {"error": f"Variant Recoder failed for {hgvs}: {response.text}"}

    data = response.json()

    if not data:
        return {"error": f"No results from Variant Recoder for {hgvs}"}

    first = data[0]

    for allele_data in first.values():
        vcf_list = allele_data.get("vcf_string", [])
        for vcf in vcf_list:
            parts = vcf.split("-")
            # filter out LRG entries — real chromosomes are numeric or X/Y/MT
            chrom = parts[0]
            if chrom.isdigit() or chrom in ("X", "Y", "MT"):
                pos = parts[1]
                ref = parts[2]
                alt = parts[3]
                return f"{chrom}-{pos}-{ref}-{alt}"

    return {"error": f"No valid genomic vcf_string found for {hgvs}"}


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