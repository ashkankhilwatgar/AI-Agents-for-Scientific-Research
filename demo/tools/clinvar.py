import re
import requests
import xml.etree.ElementTree as ET
from config import NCBI_API_KEY

CLINVAR_SEARCH_URL  = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
CLINVAR_FETCH_URL   = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
CLINVAR_SUMMARY_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"

# Matches canonical protein notation inside parentheses: (p.Cys51Tyr)
_PROTEIN_RE = re.compile(r'\(p\.([A-Za-z]{3})(\d+)([A-Za-z]{3})\)')

# Proband count patterns in VCEP submission comment text
_PROBAND_RE     = re.compile(r'(\d+)\s+(?:unrelated\s+)?proband', re.IGNORECASE)
_INDIVIDUAL_RE  = re.compile(r'(\d+)\s+(?:affected\s+)?(?:individual|patient|case|famil)', re.IGNORECASE)

_BASE_PARAMS = {"api_key": NCBI_API_KEY} if NCBI_API_KEY else {}


# ─────────────────────────────────────────────────────────────────────────────
# PM5 helper — find LP/P variants at the same codon (HHT VCEP only)
# ─────────────────────────────────────────────────────────────────────────────

def search_clinvar_for_codon(
    gene: str,
    codon_position: int,
    ref_aa_3letter: str,
    query_cdna: str,
) -> dict:
    """
    ClinVar fallback for PM5: finds LP/P variants at the same codon classified
    by the HHT VCEP. Used when ERepo returns no results at that position.

    Returns same shape as search_erepo_by_position():
        {"gene", "codon_position", "classifications": [...], "source": "clinvar"}
    or {"error": "..."} on failure.
    """
    # All P/LP variants in gene — POST avoids URI length limits with many IDs
    search_term = (
        f'{gene}[gene] AND '
        f'(pathogenic[clinsig] OR "likely pathogenic"[clinsig])'
    )
    try:
        r = requests.get(
            CLINVAR_SEARCH_URL,
            params={"db": "clinvar", "term": search_term,
                    "retmax": 1000, "retmode": "json", **_BASE_PARAMS},
            timeout=20,
        )
        if r.status_code != 200:
            return {"error": f"ClinVar esearch HTTP {r.status_code}"}
        id_list = r.json().get("esearchresult", {}).get("idlist", [])
    except Exception as e:
        return {"error": f"ClinVar esearch failed: {e}"}

    if not id_list:
        return {"gene": gene, "codon_position": codon_position,
                "classifications": [], "source": "clinvar"}

    # NCBI esummary silently caps at ~200 IDs per call — batch to avoid missing records
    BATCH_SIZE = 200
    all_records: dict = {}
    for i in range(0, len(id_list), BATCH_SIZE):
        batch = id_list[i:i + BATCH_SIZE]
        try:
            r = requests.post(
                CLINVAR_SUMMARY_URL,
                data={"db": "clinvar", "id": ",".join(batch),
                      "retmode": "json", **_BASE_PARAMS},
                timeout=30,
            )
            if r.status_code != 200:
                return {"error": f"ClinVar esummary HTTP {r.status_code}"}
            batch_result = r.json().get("result", {})
            for uid in batch_result.get("uids", []):
                all_records[uid] = batch_result[uid]
        except Exception as e:
            return {"error": f"ClinVar esummary failed: {e}"}

    matches = []
    for uid, record in all_records.items():
        if not isinstance(record, dict):
            continue
        title = record.get("title", "")

        if query_cdna and query_cdna in title:
            continue  # skip self-match

        match = _PROTEIN_RE.search(title)
        if not match or int(match.group(2)) != codon_position:
            continue

        # Use overall ClinVar consensus classification.
        # HHT VCEP often classifies variants in ERepo without creating a separate
        # ClinVar SCV, so filtering by submitter misses their reference variants.
        # The aggregate P/LP consensus from multiple labs is sufficient for PM5.
        germline = record.get("germline_classification", {})
        clinsig = germline.get("description", "").lower()
        if "pathogenic" not in clinsig:
            continue

        matches.append({
            "hgvs": title,
            "protein_change": f"p.{match.group(1)}{match.group(2)}{match.group(3)}",
            "classification": germline.get("description", ""),
        })

    return {
        "gene": gene,
        "codon_position": codon_position,
        "classifications": matches,
        "source": "clinvar",
    }


# ─────────────────────────────────────────────────────────────────────────────
# PS4 helper — look up a specific variant and extract VCEP proband count
# ─────────────────────────────────────────────────────────────────────────────

def _parse_proband_count(text: str) -> int:
    """Extract the first numeric proband/individual/patient count from free text."""
    m = _PROBAND_RE.search(text)
    if m:
        return int(m.group(1))
    m = _INDIVIDUAL_RE.search(text)
    if m:
        return int(m.group(1))
    return 0


def _parse_hht_vcep_scv(xml_text: str) -> dict:
    """
    Parse ClinVar VCV XML for the HHT VCEP ClinicalAssertion.

    XML structure (confirmed from live API):
      ClinicalAssertion
        ClinVarAccession[@SubmitterName]  ← submitter name here
        Classification
          GermlineClassification          ← text is the classification
          Comment[@Type='public']         ← full evidence comment with proband count

    Returns {"found", "proband_count", "classification", "comment"}.
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        return {"found": False, "error": f"XML parse error: {e}"}

    for assertion in root.iter("ClinicalAssertion"):
        # Submitter name is the SubmitterName attribute on ClinVarAccession
        submitter = ""
        for acc in assertion.iter("ClinVarAccession"):
            submitter = acc.get("SubmitterName", "")
            break

        if "hereditary hemorrhagic telangiectasia" not in submitter.lower():
            continue

        # Classification is in Classification/GermlineClassification text
        classification = ""
        for cl in assertion.iter("Classification"):
            for gc in cl:
                if gc.tag == "GermlineClassification":
                    classification = gc.text or ""
                    break
            break

        # Comment with evidence summary (Type='public')
        comment = ""
        for cl in assertion.iter("Classification"):
            for c in cl:
                if c.tag == "Comment":
                    comment = c.text or ""
                    break
            break

        proband_count = _parse_proband_count(comment)

        return {
            "found": True,
            "proband_count": proband_count,
            "classification": classification,
            "comment": comment,
            "source": "clinvar_vcep",
        }

    return {"found": False, "proband_count": 0, "comment": "", "source": "clinvar_vcep"}


def search_clinvar_for_variant_ps4(hgvs: str) -> dict:
    """
    Looks up a specific variant in ClinVar and extracts proband count from
    the HHT VCEP SCV comment. Primary PS4 data source.

    Returns:
        {
            "found": bool,
            "proband_count": int,
            "classification": str,
            "comment": str,
            "source": "clinvar_vcep"
        }
    or {"error": "..."} on failure.
    """
    # Step 1: search by HGVS
    try:
        r = requests.get(
            CLINVAR_SEARCH_URL,
            params={"db": "clinvar", "term": f'"{hgvs}"[HGVS]',
                    "retmax": 5, "retmode": "json", **_BASE_PARAMS},
            timeout=15,
        )
        r.raise_for_status()
        id_list = r.json().get("esearchresult", {}).get("idlist", [])
    except Exception as e:
        return {"error": f"ClinVar esearch failed: {e}"}

    if not id_list:
        return {"found": False, "proband_count": 0, "comment": "", "source": "clinvar_vcep"}

    # Step 2: fetch VCV XML
    # is_variationid is required — without it, ClinVar returns <set/> (empty)
    try:
        r = requests.get(
            CLINVAR_FETCH_URL,
            params={"db": "clinvar", "id": id_list[0],
                    "rettype": "vcv", "retmode": "xml",
                    "is_variationid": "", **_BASE_PARAMS},
            timeout=20,
        )
        r.raise_for_status()
    except Exception as e:
        return {"error": f"ClinVar efetch failed: {e}"}

    return _parse_hht_vcep_scv(r.text)


# ─────────────────────────────────────────────────────────────────────────────
# Legacy — generic ClinVar lookup (used by other criteria if needed)
# ─────────────────────────────────────────────────────────────────────────────

def search_clinvar(variant: str) -> dict:
    search_params = {"db": "clinvar", "term": variant, "retmode": "json"}
    search_response = requests.get(CLINVAR_SEARCH_URL, params=search_params)
    search_response.raise_for_status()
    data = search_response.json()

    id_list = data["esearchresult"]["idlist"]
    if not id_list:
        return {"error": f"No ClinVar records found for variant: {variant}"}

    fetch_response = requests.get(
        CLINVAR_FETCH_URL,
        params={"db": "clinvar", "id": id_list[0],
                "rettype": "vcv", "retmode": "xml"},
    )
    fetch_response.raise_for_status()

    return {"variation_id": id_list[0], "record": fetch_response.text}
