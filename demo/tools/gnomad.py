import requests
import time
from langchain_core.rate_limiters import InMemoryRateLimiter
from config import GNOMAD_REQUESTS_PER_MINUTE

GNOMAD_URL = "https://gnomad.broadinstitute.org/api"
MAX_RETRIES = 4
RETRY_DELAY = 3

# gnomAD's public API has no documented rate limit, but returns HTTP 429 when
# several variants' BA1/BS1/PP2/BP1 queries land at the same instant — which
# happens routinely now that variants run concurrently (see run_pipeline_batch
# in pipeline.py). This limiter is shared by every call in this module,
# regardless of which thread/variant it's for, so all gnomAD requests across
# the whole process are serialized into a steady trickle instead of a burst.
# InMemoryRateLimiter is thread-safe internally (same pattern used for the
# Gemini rate limiter in agents/llm/llm.py).
_gnomad_rate_limiter = InMemoryRateLimiter(
    requests_per_second=GNOMAD_REQUESTS_PER_MINUTE / 60,
    check_every_n_seconds=0.1,
    max_bucket_size=1,  # no bursts — a strict trickle
)


def _gnomad_post(payload: dict):
    """
    Rate-limited, retrying POST to the gnomAD API shared by every query
    function in this module.

    Every attempt — including retries — first acquires a token from the
    shared rate limiter, so a burst of 429s can't be caused by retries
    themselves piling back up. Honors a Retry-After header when gnomAD sends
    one; otherwise backs off with an increasing delay.

    Returns (response, None) on a request that got an HTTP response at all
    (caller still needs to check status_code/JSON body), or (None, error_str)
    if every retry failed outright (network error or persistent 429/500/503).
    """
    last_error = "No attempts completed"

    for attempt in range(MAX_RETRIES):
        _gnomad_rate_limiter.acquire()

        try:
            response = requests.post(GNOMAD_URL, json=payload, timeout=15)
        except requests.RequestException as e:
            last_error = str(e)
            time.sleep(RETRY_DELAY * (attempt + 1))
            continue

        if response.status_code in (429, 500, 503):
            last_error = f"HTTP {response.status_code}"
            retry_after = response.headers.get("Retry-After")
            wait = None
            if retry_after:
                try:
                    wait = float(retry_after)
                except ValueError:
                    wait = None
            if wait is None:
                wait = RETRY_DELAY * (attempt + 1)
            time.sleep(wait)
            continue

        return response, None

    return None, f"gnomAD API failed after {MAX_RETRIES} retries: {last_error}"


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

    response, error = _gnomad_post(payload)
    if error:
        return {"error": error}

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

    response, error = _gnomad_post(payload)
    if error:
        return {"error": error}

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
