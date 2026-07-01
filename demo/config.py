from dotenv import load_dotenv

# override=True: by default python-dotenv will NOT overwrite a variable that's
# already set in the shell environment. If GOOGLE_API_KEY (or another key) was
# ever `export`ed in a shell session, or set by another tool, .env would be
# silently ignored and the stale value would keep being used.
load_dotenv(override=True)




NCBI_API_KEY = "cfe8c362c0505fe8ea3f0f9893d80c3f8208"
NCBI_EMAIL = "sli1@hamilton.edu"


# If you think the functional evidence tools is too slow, you can 
# switch to a smaller model for functional evidence. However, note that
# The functional evidence tool requires heavy thinking. The smaller model 
# may be less accurate

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


OLLAMA_BASE_URL="http://150.209.23.239:11434"

RETRY_LIMIT=2

# Free-tier Gemini quota is 5 requests/minute PER MODEL
# (generativelanguage.googleapis.com/generate_content_free_tier_requests).
# Our LangGraph pipeline fans criteria out in parallel, so several agents can
# try to call the same Gemini model within the same minute. The LLM wrapper
# throttles calls to this rate so they queue instead of getting 429'd.
# Raise this if you move to a paid tier with a higher requests-per-minute limit.
GEMINI_REQUESTS_PER_MINUTE = 5




