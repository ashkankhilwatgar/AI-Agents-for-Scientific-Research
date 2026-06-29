import re
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


# Regex for intronic HGVS offset notation: c.NNN+/-NNN or c.*NNN+/-NNN
_INTRONIC_RE = re.compile(r'c\.\*?(\d+)([+-])(\d+)')


def _classify_hgvs_directly(variant: str) -> dict | None:
    """
    Classifies a variant from its HGVS cDNA notation without calling VEP.
    Returns a get_variant_type-compatible dict, or None if the notation
    doesn't allow unambiguous classification (e.g. it's not intronic).

    Intronic offset rules (HGVS standard):
      +/-1, +/-2  → splice_site    (canonical GT-AG dinucleotide)
      +/-3 to +/-8 → splice_region  (near-splice, may affect splicing)
      +/-9 and beyond → intronic    (deep intronic)
    """
    if ":" not in variant:
        return None
    cdna = variant.split(":", 1)[1]  # e.g. "c.1377+4A>T"
    m = _INTRONIC_RE.search(cdna)
    if not m:
        return None  # not intronic — let VEP classify it
    offset = int(m.group(3))
    if offset <= 2:
        direction = m.group(2)
        raw = "splice_donor_variant" if direction == "+" else "splice_acceptor_variant"
        return {"variant_type": "splice_site", "raw_consequence": raw}
    elif offset <= 8:
        return {"variant_type": "splice_region", "raw_consequence": "splice_region_variant"}
    else:
        return {"variant_type": "intronic", "raw_consequence": "intron_variant"}


def get_variant_type(variant: str) -> dict:
    """
    Determines variant consequence type.
    For intronic HGVS (c.NNN+/-NNN), classifies directly from the notation
    without calling VEP — VEP's most_severe_consequence is computed across
    all overlapping transcripts and will misclassify intronic variants when
    another transcript has a coding exon at the same position.
    For all other variants, falls back to Ensembl VEP.

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

    # Fast path: intronic HGVS can be classified from notation alone.
    # We DON'T return immediately — we still call VEP to extract gene_symbol,
    # then override variant_type/raw_consequence with the fast-path result.
    direct = _classify_hgvs_directly(variant) if is_hgvs else None

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

        # Prefer the consequence for the input transcript when HGVS is given.
        # most_severe_consequence is computed across ALL overlapping transcripts —
        # a more severe consequence in a different transcript (e.g. missense in an
        # overlapping coding exon) will dominate and misclassify intronic/splice variants.
        raw_consequence = None
        matched_tc = None

        if is_hgvs and variant.startswith("NM_") and ":" in variant:
            # Extract transcript base ID without version (e.g. "NM_000020.3" → "NM_000020")
            transcript_base = variant.split(":")[0].split(".")[0]
            tcs = data[0].get("transcript_consequences", [])
            # Find the consequence entry for the input transcript
            matched_tc = next(
                (tc for tc in tcs
                 if tc.get("transcript_id", "").startswith(transcript_base)),
                None
            )
            if matched_tc:
                terms = matched_tc.get("consequence_terms", [])
                # Pick the most severe term for this transcript using CONSEQUENCE_MAP priority
                _SEVERITY_ORDER = list(CONSEQUENCE_MAP.keys())
                best = None
                for term in terms:
                    if best is None or best not in _SEVERITY_ORDER or (term in _SEVERITY_ORDER and
                            _SEVERITY_ORDER.index(term) < _SEVERITY_ORDER.index(best)):
                        best = term
                raw_consequence = best

        # Fallback: use VEP's global most_severe_consequence
        if not raw_consequence:
            raw_consequence = data[0].get("most_severe_consequence", "")

        if not raw_consequence:
            return {"error": "VEP response missing most_severe_consequence field"}


        gene_sym = None
        if matched_tc:
            gene_sym = matched_tc.get("gene_symbol")
        elif data[0].get("transcript_consequences"):
            gene_sym = data[0]["transcript_consequences"][0].get("gene_symbol")

        # If fast path already classified variant_type more accurately, use it
        # but add gene_symbol from VEP.
        if direct is not None:
            direct["gene_symbol"] = gene_sym
            return direct

        return {
            "variant_type": CONSEQUENCE_MAP.get(raw_consequence, "other"),
            "raw_consequence": raw_consequence,
            "gene_symbol": gene_sym
        }

    # If fast path classified the variant but VEP failed (network error etc.),
    # still return the fast-path result with gene_symbol=None rather than an error.
    if direct is not None:
        direct["gene_symbol"] = None
        return direct

    return {"error": f"Ensembl VEP failed after {MAX_RETRIES} retries: {last_error}"}

def _fetch_ref_base(nc_accession_or_chrom: str, pos_1based: int) -> str:
    """
    Fetches a single reference nucleotide from the Ensembl REST API.

    Accepts either:
      - An NC_ accession (e.g. "NC_000009.12") — resolved to chromosome name internally
      - A bare chromosome name (e.g. "9", "X") — used directly

    pos_1based: 1-based genomic position (GRCh38)
    Returns the nucleotide string, or {"error": "..."} on failure.
    """
    if nc_accession_or_chrom.startswith("NC_"):
        nc_prefix = nc_accession_or_chrom.split(".")[0]
        chrom = _NC_TO_CHROM.get(nc_prefix)
        if chrom is None:
            return {"error": f"_fetch_ref_base: unrecognised NC_ accession {nc_accession_or_chrom}"}
    else:
        chrom = nc_accession_or_chrom

    url = f"{ENSEMBL_URL}/sequence/region/human/{chrom}:{pos_1based}-{pos_1based}:1"
    last_error = "No attempts completed"

    for attempt in range(MAX_RETRIES):
        try:
            r = requests.get(
                url,
                headers={"Content-Type": "application/json"},
                timeout=15
            )
            if r.status_code in (429, 500, 503):
                last_error = f"HTTP {r.status_code}"
                time.sleep(RETRY_DELAY * (attempt + 1))
                continue
            if r.status_code != 200:
                last_error = f"HTTP {r.status_code}: {r.text}"
                continue
            seq = r.json().get("seq", "")
            if not seq:
                return {"error": f"_fetch_ref_base: empty sequence returned for {chrom}:{pos_1based}"}
            return seq[0].upper()
        except requests.RequestException as e:
            last_error = str(e)
            time.sleep(RETRY_DELAY)

    return {"error": f"_fetch_ref_base: Ensembl failed after {MAX_RETRIES} retries: {last_error}"}


def _hgvs_to_gnomad_via_vep(hgvs: str) -> str:
    """
    Fallback coordinate resolver using Ensembl VEP.
    Used when NCBI Variation Services rejects the HGVS (e.g. intronic variants).

    VEP returns seq_region_name (chrom), start (1-based), and allele_string (REF/ALT).
    For substitutions (no '-'): constructs gnomAD format directly.
    For indels ('-' in ref or alt): applies VCF anchor normalisation via _fetch_ref_base.

    Returns gnomAD format string, or {"error": "..."} on failure.
    """
    encoded = quote(hgvs, safe="")
    last_error = "No attempts completed"

    for attempt in range(MAX_RETRIES):
        try:
            r = requests.get(
                f"{ENSEMBL_URL}/vep/human/hgvs/{encoded}",
                headers={"Content-Type": "application/json"},
                timeout=15,
                params={"refseq": 1}
            )
            if r.status_code in (429, 500, 503):
                last_error = f"HTTP {r.status_code}"
                time.sleep(RETRY_DELAY * (attempt + 1))
                continue
            if r.status_code != 200:
                return {"error": f"VEP fallback failed for {hgvs}: HTTP {r.status_code}"}

            data = r.json()
            if not data or not isinstance(data, list):
                return {"error": f"VEP fallback: empty response for {hgvs}"}

            hit = data[0]
            chrom = str(hit.get("seq_region_name", ""))
            pos   = hit.get("start")
            allele_string = hit.get("allele_string", "")

            if not chrom or pos is None or not allele_string:
                return {"error": f"VEP fallback: missing coordinates in response for {hgvs}"}

            parts = allele_string.split("/")
            if len(parts) != 2:
                return {"error": f"VEP fallback: unexpected allele_string '{allele_string}' for {hgvs}"}

            ref_raw, alt_raw = parts

            # VEP uses '-' to represent absent sequence in indels — convert to empty string
            ref = "" if ref_raw == "-" else ref_raw
            alt = "" if alt_raw == "-" else alt_raw

            # Apply VCF anchor normalisation if either side is empty
            if ref == "" or alt == "":
                anchor_pos = pos - 1  # pos is already 1-based; anchor is one to the left
                anchor_base = _fetch_ref_base(chrom, anchor_pos)
                if isinstance(anchor_base, dict):
                    return anchor_base
                ref = anchor_base + ref
                alt = anchor_base + alt
                pos = anchor_pos

            return f"{chrom}-{pos}-{ref}-{alt}"

        except requests.RequestException as e:
            last_error = str(e)
            time.sleep(RETRY_DELAY)
            continue

    return {"error": f"VEP fallback failed after {MAX_RETRIES} retries: {last_error}"}


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
    # NCBI does not support intronic positions (c.X+N / c.X-N) — fall back to VEP for those.
    spdi = None
    ncbi_400 = False
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
            if r.status_code == 400:
                ncbi_400 = True
                break  # not a transient error — try VEP fallback immediately
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

    if ncbi_400:
        result = _hgvs_to_gnomad_via_vep(hgvs)
        if not isinstance(result, dict):
            _RECODER_CACHE[hgvs] = result
        return result

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

    spdi_pos = genomic_spdi["position"]  # 0-based
    ref = genomic_spdi["deleted_sequence"]
    alt = genomic_spdi["inserted_sequence"]

    # --- Step 4: VCF anchor normalisation for indels ---
    # gnomAD uses VCF conventions: pure deletions (alt="") and pure insertions (ref="")
    # must include a left-anchor base so neither ref nor alt is empty.
    # SPDI position is 0-based; anchor sits at position-1 (0-based) = position (1-based).
    if ref == "" or alt == "":
        anchor_pos_0based = spdi_pos - 1
        anchor_pos_1based = anchor_pos_0based + 1
        anchor_base = _fetch_ref_base(nc_accession, anchor_pos_1based)
        if isinstance(anchor_base, dict):  # error dict
            return anchor_base
        ref = anchor_base + ref
        alt = anchor_base + alt
        pos = anchor_pos_1based  # VCF POS is 1-based position of the anchor
    else:
        pos = spdi_pos + 1  # 0-based → 1-based VCF (SNV / MNV path)

    result = f"{chrom}-{pos}-{ref}-{alt}"
    _RECODER_CACHE[hgvs] = result
    return result


def get_gene_symbol_from_transcript(transcript_id: str) -> str | None:
    """
    Fallback: maps a RefSeq transcript ID (NM_...) to a gene symbol via NCBI eutils.
    Used when VEP fails and gene_symbol cannot be extracted from VEP response.

    Returns gene symbol string, or None on failure.
    """
    bare = transcript_id.split(".")[0]  # strip version, e.g. NM_014858.4 → NM_014858

    try:
        # Step 1: transcript accession → NCBI Gene ID
        r1 = requests.get(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
            params={"db": "gene", "term": f"{bare}[accn]", "retmode": "json"},
            timeout=10,
        )
        if r1.status_code != 200:
            return None
        ids = r1.json().get("esearchresult", {}).get("idlist", [])
        if not ids:
            return None
        gene_id = ids[0]

        # Step 2: Gene ID → gene symbol
        r2 = requests.get(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
            params={"db": "gene", "id": gene_id, "retmode": "json"},
            timeout=10,
        )
        if r2.status_code != 200:
            return None
        result = r2.json().get("result", {})
        gene_info = result.get(gene_id, {})
        symbol = gene_info.get("name") or gene_info.get("nomenclaturesymbol")
        return symbol or None

    except Exception:
        return None


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

    try:
        return json.loads(text[start:end])
    except json.JSONDecodeError:
        return {
            "pass": False,
            "error_type": "reasoning",
            "feedback": "Judge agent received malformed JSON from model"
        }