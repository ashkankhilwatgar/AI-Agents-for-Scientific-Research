import re
import requests

EREPO_URL = "https://erepo.clinicalgenome.org/evrepo/api/classifications"
HHT_VCEP_AFFILIATION = "Hereditary Hemorrhagic Telangiectasia VCEP"
MAX_RETRIES = 3
PAGE_SIZE = 100
MAX_PAGES = 20  # safety ceiling — 2000 entries far exceeds any single gene

# Matches canonical HGVS protein notation: (p.Ser186Ile)
PROTEIN_CHANGE_RE = re.compile(r'\(p\.([A-Za-z]{3})(\d+)([A-Za-z]{3})\)')


def _extract_canonical_hgvs(hgvs_list: list, gene: str) -> str | None:
    """
    Returns the canonical HGVS entry — the one containing ({gene}) and (p.XxxNNNYyy).
    This is always the last entry in the ERepo HGVS array.
    """
    for h in reversed(hgvs_list):
        if f"({gene})" in h and "(p." in h:
            return h
    return None


def _parse_protein_position(canonical_hgvs: str) -> int | None:
    """Extracts protein position from e.g. NM_000020.3(ACVRL1):c.557G>T (p.Ser186Ile) → 186"""
    match = PROTEIN_CHANGE_RE.search(canonical_hgvs)
    return int(match.group(2)) if match else None


def _parse_protein_change(canonical_hgvs: str) -> str | None:
    """Extracts protein change from canonical HGVS → 'p.Ser186Ile'"""
    match = PROTEIN_CHANGE_RE.search(canonical_hgvs)
    return f"p.{match.group(1)}{match.group(2)}{match.group(3)}" if match else None


def _get_hht_vcep_classification(entry: dict) -> tuple[bool, str]:
    """
    Returns (True, classification_label) if the entry has an HHT VCEP classification,
    otherwise (False, "").
    """
    for guideline in entry.get("guidelines", []):
        for agent in guideline.get("agents", []):
            if agent.get("affiliation") == HHT_VCEP_AFFILIATION:
                label = guideline.get("outcome", {}).get("label", "Unknown")
                return True, label
    return False, ""


def search_erepo_by_position(gene: str, codon_position: int) -> dict:
    """
    Returns all HHT VCEP-classified variants for the given gene at the given
    protein position, fetched via paginated ERepo API queries.

    The ERepo API does not support server-side filtering by protein position,
    so all gene entries are fetched and filtered client-side.

    Returns:
        {
            "gene": str,
            "codon_position": int,
            "classifications": [
                {
                    "hgvs": str,           # canonical NM_ form with protein notation
                    "protein_change": str, # e.g. "p.Ser186Ile"
                    "classification": str, # "Pathogenic" | "Likely Pathogenic" | etc.
                },
                ...
            ]
        }

    Returns {"error": "..."} on unrecoverable failure — never raises.
    """
    matches = []
    start = 0

    for _ in range(MAX_PAGES):
        params = {"gene": gene, "limit": PAGE_SIZE, "start": start}
        last_error = "No attempts completed"
        page = None

        for _ in range(MAX_RETRIES):
            try:
                r = requests.get(EREPO_URL, params=params, timeout=20)
                if r.status_code != 200:
                    last_error = f"{r.status_code}: {r.text[:200]}"
                    continue
                page = r.json().get("variantInterpretations", [])
                break
            except requests.RequestException as e:
                last_error = str(e)
                continue

        if page is None:
            return {"error": f"ERepo API failed after {MAX_RETRIES} retries: {last_error}"}

        if not page:
            break  # exhausted all entries

        for entry in page:
            canonical = _extract_canonical_hgvs(entry.get("hgvs", []), gene)
            if not canonical:
                continue
            if _parse_protein_position(canonical) != codon_position:
                continue
            is_vcep, classification = _get_hht_vcep_classification(entry)
            if not is_vcep:
                continue
            matches.append({
                "hgvs": canonical,
                "protein_change": _parse_protein_change(canonical),
                "classification": classification,
            })

        if len(page) < PAGE_SIZE:
            break  # last page
        start += PAGE_SIZE

    return {
        "gene": gene,
        "codon_position": codon_position,
        "classifications": matches,
    }
