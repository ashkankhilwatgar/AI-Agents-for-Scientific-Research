import requests
import xml.etree.ElementTree as ET
from config import NCBI_API_KEY

ENTREZ_SEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
ENTREZ_FETCH_URL  = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
MAX_RESULTS  = 10
MAX_RETRIES  = 3
ENTREZ_EMAIL = "akhilwat@hamilton.edu"


def search_pubmed(variant: str) -> dict:
    """
    Searches PubMed for case reports of the given variant in HHT patients.

    Query: "{variant} AND HHT AND ACVRL1"

    Returns:
        {
            "query": str,
            "total_found": int,
            "articles": [
                {"pmid": str, "title": str, "abstract": str},
                ...
            ]
        }

    Returns {"error": "..."} on unrecoverable failure — never raises.
    """
    query = f"{variant} AND HHT AND ACVRL1"

    # --- Step 1: esearch — get PMIDs ---
    search_params = {
        "db":      "pubmed",
        "term":    query,
        "retmax":  MAX_RESULTS,
        "retmode": "json",
        "email":   ENTREZ_EMAIL,
        "api_key": NCBI_API_KEY,
    }

    last_error = "No attempts completed"

    for _ in range(MAX_RETRIES):
        try:
            r = requests.get(ENTREZ_SEARCH_URL, params=search_params, timeout=15)
            if r.status_code != 200:
                last_error = f"{r.status_code}: {r.text}"
                continue
            data = r.json()
            id_list = data.get("esearchresult", {}).get("idlist", [])
            total   = int(data.get("esearchresult", {}).get("count", 0))
            break
        except requests.RequestException as e:
            last_error = str(e)
            continue
    else:
        return {"error": f"PubMed esearch failed after {MAX_RETRIES} retries: {last_error}"}

    if not id_list:
        return {
            "query":       query,
            "total_found": 0,
            "articles":    [],
        }

    # --- Step 2: efetch — get titles + abstracts ---
    fetch_params = {
        "db":      "pubmed",
        "id":      ",".join(id_list),
        "rettype": "abstract",
        "retmode": "xml",
        "email":   ENTREZ_EMAIL,
        "api_key": NCBI_API_KEY,
    }

    for _ in range(MAX_RETRIES):
        try:
            r = requests.get(ENTREZ_FETCH_URL, params=fetch_params, timeout=15)
            if r.status_code != 200:
                last_error = f"{r.status_code}: {r.text}"
                continue
            articles = _parse_pubmed_xml(r.text)
            return {
                "query":       query,
                "total_found": total,
                "articles":    articles,
            }
        except requests.RequestException as e:
            last_error = str(e)
            continue

    return {"error": f"PubMed efetch failed after {MAX_RETRIES} retries: {last_error}"}


def _parse_pubmed_xml(xml_text: str) -> list[dict]:
    """
    Parses PubMed efetch XML and extracts PMID, title, and abstract for each article.
    Returns a list of dicts. Missing fields are returned as empty strings.
    """
    articles = []

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    for article in root.findall(".//PubmedArticle"):
        pmid_el    = article.find(".//PMID")
        title_el   = article.find(".//ArticleTitle")
        abstract_el = article.find(".//AbstractText")

        pmid     = pmid_el.text.strip()    if pmid_el     is not None else ""
        title    = title_el.text.strip()   if title_el    is not None else ""
        abstract = abstract_el.text.strip() if abstract_el is not None and abstract_el.text else ""

        articles.append({
            "pmid":     pmid,
            "title":    title,
            "abstract": abstract,
        })

    return articles
