from dotenv import load_dotenv
import os

load_dotenv()

# =============================================================================
# LLM Provider Configuration
# =============================================================================

# PLan agent
PLAN_AGENT_PROVIDER = os.getenv("PLAN_AGENT_PROVIDER", "ollama")
PLAN_AGENT_MODEL = os.getenv("PLAN_AGENT_MODEL", "deepseek-r1:32b")
PLAN_AGENT_TEMPERATURE = float(os.getenv("PLAN_AGENT_TEMPERATURE", 0))

# Task agent
TASK_AGENT_PROVIDER = os.getenv("TASK_AGENT_PROVIDER", "ollama")
TASK_AGENT_MODEL = os.getenv("TASK_AGENT_MODEL", "qwen2.5:14b")
TASK_AGENT_TEMPERATURE = float(os.getenv("TASK_AGENT_TEMPERATURE", 0))

# Debug agent
DEBUG_AGENT_PROVIDER = os.getenv("DEBUG_AGENT_PROVIDER", "ollama")
DEBUG_AGENT_MODEL = os.getenv("DEBUG_AGENT_MODEL", "qwen2.5:7b")
DEBUG_AGENT_TEMPERATURE = float(os.getenv("DEBUG_AGENT_TEMPERATURE", 0))

# Check agent
CHECK_AGENT_PROVIDER = os.getenv("CHECK_AGENT_PROVIDER", "ollama")
CHECK_AGENT_MODEL = os.getenv("CHECK_AGENT_MODEL", "qwen2.5:7b")
CHECK_AGENT_TEMPERATURE = float(os.getenv("CHECK_AGENT_TEMPERATURE", 0))

# Judge agent
JUDGE_AGENT_PROVIDER = os.getenv("JUDGE_AGENT_PROVIDER", "ollama")
JUDGE_AGENT_MODEL = os.getenv("JUDGE_AGENT_MODEL", "deepseek-r1:32b")
JUDGE_AGENT_TEMPERATURE = float(os.getenv("JUDGE_AGENT_TEMPERATURE", 0))



# # Model selection
# MODELS = {
#     "plan":  "deepseek-r1:32b",
#     "task":  "qwen2.5:14b",
#     "debug": "qwen2.5:7b",
#     "judge": "deepseek-r1:32b",
#     "check": "qwen2.5:7b",
# }

RETRY_LIMIT = int(os.getenv("RETRY_LIMIT", 2))

NCBI_API_KEY= os.getenv("NCBI_API_KEY")
NCBI_EMAIL = os.getenv("NCBI_EMAIL")

# =============================================================================
# Safeguard against missing api keys & base urls
# =============================================================================

providers = [
    PLAN_AGENT_PROVIDER, TASK_AGENT_PROVIDER, DEBUG_AGENT_PROVIDER, 
    JUDGE_AGENT_PROVIDER, CHECK_AGENT_PROVIDER
    ]


for provider in providers:

    if provider.lower().strip() == "openai":
        if not os.getenv("OPENAI_API_KEY"):
            raise ValueError(
                "OpenAI API key must be set in the .env file"
            )
    elif provider.lower().strip() == "google":
        if not os.getenv("GOOGLE_API_KEY"):
            raise ValueError(
                "Gemini API key must be set in the .env file"
            )
    # Technically speaking we don't need Ollama url here, but just
    # to be consistent we will also check whether the base url of ollama
    elif provider.lower().strip() == "ollama":
        if not os.get("OLLAMA_BASE_URL"):
            raise ValueError(
                "Local model base url must be set in the .env file"
            )
        
    else:
        raise ValueError(
            f"Unsupported LLM provider: {provider}. "
            "Supported Providers: local, openai, gemini"
        )

