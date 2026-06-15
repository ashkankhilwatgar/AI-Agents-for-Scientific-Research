import requests

CLINVAR_SEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
CLINVAR_FETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

def search_clinvar(variant: str) -> dict:
    search_params = {
        "db": "clinvar",
        "term": variant,
        "retmode": "json"
    }
    search_response = requests.get(CLINVAR_SEARCH_URL, params=search_params)
    search_response.raise_for_status()
    data = search_response.json()

    id_list = data["esearchresult"]["idlist"]
    if not id_list:
        return {"error": f"No ClinVar records found for variant: {variant}"}

    variation_id = id_list[0]

    fetch_params = {
        "db": "clinvar",
        "id": variation_id,
        "rettype": "vcv",
        "retmode": "xml"
    }
    fetch_response = requests.get(CLINVAR_FETCH_URL, params=fetch_params)
    fetch_response.raise_for_status()

    return {
        "variation_id": variation_id,
        "record": fetch_response.text
    }