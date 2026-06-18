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
                ac_hom
                filters
                populations {
                    id
                    ac
                    an
                    ac_hom
                }
                faf95 {
                    popmax
                    popmax_population
                }
            }
            genome {
                ac
                an
                af
                ac_hom
                filters
                populations {
                    id
                    ac
                    an
                    ac_hom
                }
                faf95 {
                    popmax
                    popmax_population
                }
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

    variant_data = data["data"]["variant"]
    
    # Handle "variant not found" — this is valid data, not an error
    if variant_data is None:
        return {
            "found": False,
            "message": "Variant not found in gnomAD (likely rare or novel)",
            "total_ac": 0,
            "popmax_faf": 0.0,
            "ac_hom": 0,
        }
    
    # Aggregate exome + genome data for total AC and homozygote count
    exome = variant_data.get("exome") or {}
    genome = variant_data.get("genome") or {}
    
    total_ac = (exome.get("ac") or 0) + (genome.get("ac") or 0)
    total_ac_hom = (exome.get("ac_hom") or 0) + (genome.get("ac_hom") or 0)
    
    # Pull faf95.popmax — use the higher of exome/genome
    exome_faf = (exome.get("faf95") or {}).get("popmax", 0.0) or 0.0
    genome_faf = (genome.get("faf95") or {}).get("popmax", 0.0) or 0.0
    popmax_faf = max(exome_faf, genome_faf)
    
    return {
        "found": True,
        "variant_id": variant_data["variantId"],
        "total_ac": total_ac,
        "ac_hom": total_ac_hom,
        "popmax_faf": popmax_faf,
        "exome": exome,
        "genome": genome,
    }