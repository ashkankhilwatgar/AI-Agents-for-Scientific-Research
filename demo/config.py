from dotenv import load_dotenv

load_dotenv()




NCBI_API_KEY = "cfe8c362c0505fe8ea3f0f9893d80c3f8208"
NCBI_EMAIL = "sli1@hamilton.edu"

# MODELS = {
#     "plan":  {"provider": "ollama", "model": "deepseek-r1:32b"},
#     "task":  {"provider": "ollama", "model": "qwen2.5:14b"},
#     "debug": {"provider": "ollama", "model": "qwen2.5:7b"},
#     "judge": {"provider": "ollama", "model": "deepseek-r1:32b"},
#     "check": {"provider": "ollama", "model": "qwen2.5:7b"},
#     "functional_evidence": {"provider": "ollama", "model": "qwen2.5:7b"}
# }

MODELS = {
    "plan":  {"provider": "google_genai", "model": "gemini-2.5-flash"},
    "task":  {"provider": "google_genai", "model": "gemini-2.5-flash"},
    "debug": {"provider": "google_genai", "model": "gemini-2.5-flash"},
    "judge": {"provider": "google_genai", "model": "gemini-2.5-flash"},
    "check": {"provider": "google_genai", "model": "gemini-2.5-flash"},
    "functional_evidence": {"provider": "google_genai", "model": "gemini-2.5-flash"}
}


OLLAMA_BASE_URL="http://150.209.23.239:11434"

RETRY_LIMIT=2




