import requests

GNOMAD_URL = "https://gnomad.broadinstitute.org/api"

def query_gnomad(variant: str, dataset: str = "gnomad_r4") -> dict:
    query = """
    query VariantQuery($variantId: String!, $dataset: DatasetId!) {
        variant(variantId: $variantId, dataset: $dataset) {
            variantId
            exome {
                ac
                an
                af
            }
            genome {
                ac
                an
                af
            }
        }
    }
    """
    payload = {
        "query": query,
        "variables": {
            "variantId": variant,
            "dataset": dataset
        }
    }

    response = requests.post(GNOMAD_URL, json=payload)
    response.raise_for_status()
    data = response.json()

    if "errors" in data:
        return {"error": data["errors"]}

    return data["data"]["variant"]