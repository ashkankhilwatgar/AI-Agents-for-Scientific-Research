import requests
import time

GNOMAD_URL = "https://gnomad.broadinstitute.org/api"
MAX_RETRIES = 3
RETRY_DELAY = 2

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

    last_error = "No attempts completed"

    for attempt in range(MAX_RETRIES):
        try:
            response = requests.post(GNOMAD_URL, json=payload, timeout=15)

            if response.status_code in (429, 500, 503):
                last_error = f"HTTP {response.status_code}"
                time.sleep(RETRY_DELAY * (attempt + 1))
                continue

            if response.status_code != 200:
                return {"error": f"gnomAD API returned HTTP {response.status_code}"}

            data = response.json()

            if "errors" in data:
                messages = [e.get("message", "") for e in data["errors"]]
                if any("not found" in m.lower() for m in messages):
                    return {
                        "found": False,
                        "message": "Variant not found in gnomAD (likely rare or novel)",
                        "total_ac": 0,
                        "popmax_faf": 0.0,
                        "ac_hom": 0,
                    }
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

        except requests.RequestException as e:
            last_error = str(e)
            time.sleep(RETRY_DELAY)
            continue

    return {"error": f"gnomAD API failed after {MAX_RETRIES} retries: {last_error}"}


def query_gnomad_gene_constraint(gene_symbol: str) -> dict:
    """
    Fetches gene-level constraint metrics from gnomAD for PP2 and BP1 evaluation.

    Returns:
        {
            "gene_symbol": str,
            "mis_z":        float,  # missense Z-score (PP2 threshold: >= 3.09)
            "pLI":          float,  # probability LOF intolerant
            "oe_lof":       float,  # observed/expected LOF ratio
            "oe_lof_upper": float,  # LOEUF — upper bound of O/E LOF 90% CI
            "oe_mis":       float,  # observed/expected missense ratio
            "oe_mis_upper": float,
        }
    or {"error": "..."} on failure.
    """
    query_str = """
    query GeneConstraint($geneSymbol: String!) {
        gene(gene_symbol: $geneSymbol, reference_genome: GRCh38) {
            gnomad_constraint {
                mis_z
                pLI
                oe_lof
                oe_lof_upper
                oe_mis
                oe_mis_upper
            }
        }
    }
    """
    payload = {
        "query": query_str,
        "variables": {"geneSymbol": gene_symbol},
    }

    last_error = "No attempts completed"

    for attempt in range(MAX_RETRIES):
        try:
            response = requests.post(GNOMAD_URL, json=payload, timeout=15)

            if response.status_code in (429, 500, 503):
                last_error = f"HTTP {response.status_code}"
                time.sleep(RETRY_DELAY * (attempt + 1))
                continue

            if response.status_code != 200:
                return {"error": f"gnomAD API returned HTTP {response.status_code}"}

            data = response.json()

            if "errors" in data:
                return {"error": f"gnomAD gene constraint query error: {data['errors']}"}

            gene_data = (data.get("data") or {}).get("gene")
            if gene_data is None:
                return {"error": f"Gene '{gene_symbol}' not found in gnomAD"}

            constraint = gene_data.get("gnomad_constraint")
            if constraint is None:
                return {"error": f"No constraint data available for gene '{gene_symbol}' in gnomAD"}

            return {
                "gene_symbol":  gene_symbol,
                "mis_z":        constraint.get("mis_z"),
                "pLI":          constraint.get("pLI"),
                "oe_lof":       constraint.get("oe_lof"),
                "oe_lof_upper": constraint.get("oe_lof_upper"),
                "oe_mis":       constraint.get("oe_mis"),
                "oe_mis_upper": constraint.get("oe_mis_upper"),
            }

        except requests.RequestException as e:
            last_error = str(e)
            time.sleep(RETRY_DELAY)
            continue

    return {"error": f"gnomAD gene constraint query failed after {MAX_RETRIES} retries: {last_error}"}
