import requests
from urllib.parse import quote
import json

ENSEMBL_URL = "https://rest.ensembl.org"

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
    """
    Extracts and parses JSON from model response.
    Handles thinking blocks and markdown fences.
    """
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

    return json.loads(text)