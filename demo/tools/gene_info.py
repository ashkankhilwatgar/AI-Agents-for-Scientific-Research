import requests
import time

ENSEMBL_URL = "https://rest.ensembl.org"
MAX_RETRIES = 3
RETRY_DELAY = 2

_CACHE: dict[str, dict | None] = {}


def get_gene_info(gene_symbol: str) -> dict | None:
    """
    Fetches gene metadata from Ensembl REST API using gene symbol.

    Returns a dict with:
        gene_symbol        : str
        canonical_transcript: Ensembl transcript ID (MANE Select preferred)
        protein_length     : int | None  (amino acids, from Translation.length)
        total_exons        : int | None  (exon count on canonical transcript)

    Returns None on network failure or unknown gene.
    Results are cached in memory for the session.
    """
    if gene_symbol in _CACHE:
        return _CACHE[gene_symbol]

    last_error = "No attempts made"

    for attempt in range(MAX_RETRIES):
        try:
            r = requests.get(
                f"{ENSEMBL_URL}/lookup/symbol/homo_sapiens/{gene_symbol}",
                headers={"Content-Type": "application/json"},
                params={"expand": 1},
                timeout=15,
            )

            if r.status_code in (429, 500, 503):
                last_error = f"HTTP {r.status_code}"
                time.sleep(RETRY_DELAY * (attempt + 1))
                continue

            if r.status_code == 400:
                # Gene not found — cache None so we don't retry
                _CACHE[gene_symbol] = None
                return None

            if r.status_code != 200:
                last_error = f"HTTP {r.status_code}: {r.text[:200]}"
                continue

            data = r.json()
            transcripts = data.get("Transcript", [])

            if not transcripts:
                _CACHE[gene_symbol] = None
                return None

            # Prefer MANE Select → canonical protein-coding → first transcript
            canonical = None
            for t in transcripts:
                if t.get("is_mane_select") and t.get("biotype") == "protein_coding":
                    canonical = t
                    break
            if canonical is None:
                for t in transcripts:
                    if t.get("is_canonical") and t.get("biotype") == "protein_coding":
                        canonical = t
                        break
            if canonical is None:
                # last resort: first protein-coding transcript
                for t in transcripts:
                    if t.get("biotype") == "protein_coding":
                        canonical = t
                        break
            if canonical is None:
                canonical = transcripts[0]

            protein_length = None
            translation = canonical.get("Translation")
            if isinstance(translation, dict):
                protein_length = translation.get("length")

            total_exons = len(canonical.get("Exon", [])) or None

            result = {
                "gene_symbol":         gene_symbol,
                "canonical_transcript": canonical.get("id"),
                "protein_length":      protein_length,
                "total_exons":         total_exons,
            }

            _CACHE[gene_symbol] = result
            return result

        except requests.RequestException as e:
            last_error = str(e)
            time.sleep(RETRY_DELAY)
            continue

    # All retries exhausted
    print(f"GENE_INFO: Ensembl lookup failed for {gene_symbol} after {MAX_RETRIES} retries: {last_error}")
    _CACHE[gene_symbol] = None
    return None


def get_protein_length(gene_symbol: str) -> int | None:
    info = get_gene_info(gene_symbol)
    return info.get("protein_length") if info else None


def get_total_exons(gene_symbol: str) -> int | None:
    info = get_gene_info(gene_symbol)
    return info.get("total_exons") if info else None
