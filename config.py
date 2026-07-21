from dotenv import load_dotenv

# override=True: by default python-dotenv will NOT overwrite a variable that's
# already set in the shell environment. If GOOGLE_CLOUD_API_KEY (or another key)
# was ever `export`ed in a shell session, or set by another tool, .env would be
# silently ignored and the stale value would keep being used.
load_dotenv(override=True)




NCBI_API_KEY = "cfe8c362c0505fe8ea3f0f9893d80c3f8208"
NCBI_EMAIL = "sli1@hamilton.edu"

# metapub (used by the PS3/PS4 PubMed lookups) reads the NCBI key from the
# environment, not from this module. Export it here so metapub runs
# authenticated (higher NCBI rate limit) instead of warning "NCBI_API_KEY was
# not set" and throttling. Respect an already-set env value if present.
import os as _os
_os.environ.setdefault("NCBI_API_KEY", NCBI_API_KEY)
_os.environ.setdefault("NCBI_EMAIL", NCBI_EMAIL)


# If you think the functional evidence tool is too slow, you can switch to a
# smaller model for functional evidence. However, note that the functional
# evidence tool requires heavy thinking, so a smaller model may be less accurate.

# MODELS = {
#     "plan":  {"provider": "ollama", "model": "deepseek-r1:32b"},
#     "task":  {"provider": "ollama", "model": "qwen2.5:14b"},
#     "debug": {"provider": "ollama", "model": "qwen2.5:7b"},
#     "judge": {"provider": "ollama", "model": "deepseek-r1:32b"},
#     "check": {"provider": "ollama", "model": "qwen2.5:7b"},
#     "functional_evidence": {"provider": "ollama", "model": "deepseek-r1:32b"}
# }

MODELS = {
    "plan":  {"provider": "google_genai", "model": "gemini-2.5-flash"},
    "task":  {"provider": "google_genai", "model": "gemini-3.5-flash"},
    "debug": {"provider": "google_genai", "model": "gemini-2.5-flash"},
    "judge": {"provider": "google_genai", "model": "gemini-3.1-pro-preview"},
    "check": {"provider": "google_genai", "model": "gemini-2.5-flash"},
    "functional_evidence": {"provider": "google_genai", "model": "gemini-3.1-pro-preview"}
}


MODELS = {
    "plan":  {"provider": "google_genai", "model": "gemini-2.5-flash"},
    "task":  {"provider": "google_genai", "model": "gemini-3.5-flash"},
    "debug": {"provider": "google_genai", "model": "gemini-2.5-flash"},
    "judge": {"provider": "google_genai", "model": "gemini-3.5-flash"},
    "check": {"provider": "google_genai", "model": "gemini-2.5-flash"},
    "functional_evidence": {"provider": "google_genai", "model": "gemini-3.5-flash"}
}


OLLAMA_BASE_URL="http://150.209.23.239:11434"

RETRY_LIMIT=5

# Shared PER MODEL across every concurrently-running LangGraph branch (the
# limiter in agents/llm/llm.py). Keeps the parallel fan-out from bursting past
# the Gemini per-minute quota. Raised for the paid Vertex tier so the limiter
# protects against runaway bursts without serializing the parallel calls.
# Lower it if you start seeing 429s.
#
# Raised 300 -> 450 (1.5x, not 2x) on 2026-07-07: task, judge, and
# functional_evidence were consolidated onto the same model
# ("gemini-3.5-flash"), and the limiter key is per-model
# (f"google_genai:{model}" in agents/llm/llm.py), so those three agents now
# queue behind ONE shared 300/min bucket instead of task having its own.
# Went with a moderate bump rather than doubling since the real ceiling is
# Google Cloud's actual Vertex quota for this project, which isn't visible
# from this codebase — if 429s show up, drop this back toward 300-350 rather
# than pushing higher.
GEMINI_REQUESTS_PER_MINUTE = 450

# gnomAD's public GraphQL API has no published rate limit, but returns HTTP 429
# when several variants' PM2/BA1/BS1 (and gene-constraint) queries land at the
# same instant — which happens routinely in batch mode where variants run
# concurrently. This throttles gnomAD request STARTS globally across all threads
# (see the shared limiter in tools/gnomad.py). Lower it if 429s persist; raise
# it if runs feel slow and you're not seeing 429s.
GNOMAD_REQUESTS_PER_MINUTE = 60

# Ensembl's public VEP REST API (tools/vep.py) has no dedicated throttle today,
# unlike gnomAD above — it just retries on 429/500/503 with backoff. In batch
# mode, annotate_variant() gets called concurrently across variants/criteria
# (PVS1, PM1, PM4, erepo lookups, plus the top-level variant-type detection),
# and Ensembl's public API returns HTTP 500 under burst load the same way
# gnomAD returns 429. This throttles request STARTS globally across all
# threads, same pattern as _throttle_gnomad. Lower it if 500s persist; raise
# it if runs feel slow and you're not seeing 500s.
ENSEMBL_REQUESTS_PER_MINUTE = 60




