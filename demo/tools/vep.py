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


def _check_repeat_region(data: dict) -> bool:
    """
    check whether variant overlaps repeat region using
    Emsembl overlap api
    """
    if data and isinstance(data, list):
        first_transcript = data[0]
    else:
        first_transcript = {}
    
    chrom = first_transcript.get("seq_region_name")
    start = first_transcript.get("start")
    end = first_transcript.get("end")

    if not chrom or not start or not end:
        raise ValueError("Missing oordinates for repeat-region check")
    
    server = "https://rest.ensembl.org"
    ext = f"/overlap/region/human/{chrom}:{start}-{end}?feature=repeat"

    for _ in range(MAX_RETRIES):
        try: 
            r = requests.get(
                server + ext,
                headers={"Content-Type": "application/json"}
            )

            if r.status_code != 200:
                last_error = f"{r.status_code}: {r.text}"
                continue

            repeat_hits = r.json()

            if not isinstance(repeat_hits, list):
                raise RuntimeError("Unexpected API response format")
            
            return len(repeat_hits) > 0                

        except requests.RequestException as e:
            continue
    
    raise RuntimeError(f"Repeat-region api failed: {last_error}")
        




def annotate_variant(variant: str) -> dict[str, str]:
    """
    Calls Ensembl VEP to determine variant consequence type.
    Returns:
        dict with:
            - variant_consequence
            - codon_position
            - overlaps_repeat_region (only for indels)
        OR:
            {"error": "..."}
    """
    is_hgvs = variant.startswith("NM_") or "c." in variant or "p." in variant

    if is_hgvs:
        encoded = quote(variant, safe="")
        url = f"{ENSEMBL_URL}/vep/human/hgvs/{encoded}"
    else:
        # gnomAD format: chrom-pos-ref-alt → VEP region: CHROM:POS-POS:1/ALT
        parts = variant.split("-")
        if len(parts) != 4:
            return {"error": f"Unrecognised variant format for VEP lookup: {variant}"}
        chrom, pos, ref, alt = parts
        region = f"{chrom}:{pos}-{pos}:1/{alt}"
        encoded = quote(region, safe=":/-")
        url = f"{ENSEMBL_URL}/vep/human/region/{encoded}"

    response = None
    last_error = None

    for _ in range(MAX_RETRIES):    
        try:
            response = requests.get(
                url,
                # params=params,
                headers={"Content-Type": "application/json"},
                timeout=15,
                params = {
                    "refseq": 1
                }
            )

            if response.status_code != 200:
                last_error = f"{response.status_code}: {response.text}"
                continue

            data = response.json()

            result = None

            if data and isinstance(data, list):
                result = {
                    "variant_consequence": data[0]["transcript_consequences"][0]["consequence_terms"][0],
                    "codon_position": data[0]["transcript_consequences"][0]["protein_start"]
                }
                indel_variants = ["inframe_deletion", "inframe_insertion"]
                if result.get("variant_consequence") in indel_variants:
                    repeat = _check_repeat_region(data)
                    result.update({
                        "overlaps_repeat_region": repeat
                    })
                return result
      
            if not result:
                continue

        except requests.RequestException as e:
            continue
    raise ValueError(f"Variant annotation api failed: {last_error}")
