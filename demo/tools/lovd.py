import re
import requests
import time

LOVD_REST_URL = "https://databases.lovd.nl/shared/api/rest/variants/{gene}"
MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds between retries

# Simple in-process cache so repeated calls within one pipeline run
# don't re-fetch the full gene variant list each time.
_CACHE: dict[str, list] = {}


def _fetch_gene_variants(gene: str) -> list | dict:
    """
    Fetches all LOVD variant entries for the given gene symbol.
    Returns the list of variant dicts, or {"error": "..."} on failure.
    """
    if gene in _CACHE:
        return _CACHE[gene]

    url = LOVD_REST_URL.format(gene=gene)
    last_error = "No attempts completed"

    for _ in range(MAX_RETRIES):
        try:
            r = requests.get(
                url,
                params={"format": "application/json"},
                timeout=20,
                headers={"Accept": "application/json"},
            )
            if r.status_code == 429:
                last_error = "HTTP 429 rate limited"
                time.sleep(RETRY_DELAY)
                continue
            if r.status_code != 200:
                last_error = f"HTTP {r.status_code}: {r.text[:200]}"
                continue
            data = r.json()
            if not isinstance(data, list):
                last_error = f"Unexpected response format: {str(data)[:200]}"
                continue
            _CACHE[gene] = data
            return data
        except requests.RequestException as e:
            last_error = str(e)
            time.sleep(RETRY_DELAY)
            continue

    return {"error": f"LOVD API failed after {MAX_RETRIES} retries: {last_error}"}


def _extract_cdna(dna_string: str) -> str:
    """
    Extracts the c. portion from a LOVD DNA string.
    Handles both formats:
      - 'NC_000012.11(NM_000020.2):c.1377+45T>C'  →  'c.1377+45T>C'
      - 'NM_000020.2:c.557G>T'                    →  'c.557G>T'
    """
    m = re.search(r'(c\.[^\s]+)', dna_string)
    return m.group(1) if m else ""


def _cdna_matches(lovd_dna_string: str, cdna_change: str) -> bool:
    """
    Returns True if cdna_change is present within the extracted c. portion
    of a LOVD Variant/DNA string. Strips trailing whitespace from both.
    """
    extracted = _extract_cdna(lovd_dna_string)
    return cdna_change.strip() in extracted


def search_lovd_for_variant(gene: str, cdna_change: str) -> dict:
    """
    Searches LOVD for a specific variant by gene and cDNA change.
    Used by PS4 as an additional fallback after ClinVar SCV and ClinGen ERepo.

    cdna_change: the c. portion of the HGVS, e.g. "c.1377+4A>T" or "c.557G>T"

    LOVD is an observation database — it records how many times a variant has
    been submitted across participating labs. It does not carry ACMG/VCEP
    pathogenicity classifications; use Times_reported as the observation count.

    Returns:
        {
            "found":           bool,
            "times_reported":  int | None,   # number of lab submissions
            "hgvs":           str | None,    # canonical LOVD DNA string
            "transcript":     str | None,    # e.g. "NM_000020.2"
            "rna":            str | None,    # e.g. "r.?"
            "protein":        str | None,    # e.g. "p.(=)"
            "source":         "LOVD",
        }
    or {"error": "..."} on API failure.
    """
    variants = _fetch_gene_variants(gene)
    if isinstance(variants, dict) and "error" in variants:
        return variants

    for entry in variants:
        dna_list = entry.get("Variant/DNA", [])
        matched_dna = next(
            (dna for dna in dna_list if _cdna_matches(dna, cdna_change)),
            None
        )
        if matched_dna is None:
            # Also check variants_on_transcripts DNA fields directly
            for transcript, vot in entry.get("variants_on_transcripts", {}).items():
                if cdna_change.strip() in vot.get("DNA", ""):
                    matched_dna = vot["DNA"]
                    break

        if matched_dna is None:
            continue

        # Found a match — extract structured fields
        times_reported = None
        raw_count = entry.get("Times_reported")
        if raw_count is not None:
            try:
                times_reported = int(raw_count)
            except (ValueError, TypeError):
                pass

        # Find the best matching transcript and its VOT data
        transcript = None
        rna = None
        protein = None
        for tx, vot in entry.get("variants_on_transcripts", {}).items():
            if cdna_change.strip() in vot.get("DNA", ""):
                transcript = tx
                rna = vot.get("RNA")
                protein = vot.get("protein")
                break
        if transcript is None and entry.get("variants_on_transcripts"):
            # Fall back to first transcript in entry
            transcript = next(iter(entry["variants_on_transcripts"]))
            vot = entry["variants_on_transcripts"][transcript]
            rna = vot.get("RNA")
            protein = vot.get("protein")

        return {
            "found": True,
            "times_reported": times_reported,
            "hgvs": matched_dna,
            "transcript": transcript,
            "rna": rna,
            "protein": protein,
            "source": "LOVD",
        }

    return {
        "found": False,
        "times_reported": None,
        "hgvs": None,
        "transcript": None,
        "rna": None,
        "protein": None,
        "source": "LOVD",
    }
