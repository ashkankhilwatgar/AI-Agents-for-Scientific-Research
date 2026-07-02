from typing import Optional
from langchain_core.messages import HumanMessage, SystemMessage
import os
from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel



def create_llm(provider: str, model: str, temperature: float = 0) -> BaseChatModel:
    """
    Create and return a LangChain chat model wrapper.

    Parameters
    ----------
    provider : str
        Which backend/provider to use. Supported values are:
        - "openai"
        - "google_genai"
        - "ollama"
    model : str
        The model name for the selected provider.
        For Ollama, this must match a model installed locally, such as the names
        shown by `ollama list`.
    temperature : float, optional
        Controls randomness in model output. Lower values make output more deterministic.

    Returns
    -------
    BaseChatModel
        A LangChain chat model object that can be called with .invoke().

    Returns
    -------
    Note: If you want to use z.ai's models such as glm5.2, use openai as the model provider
    and use z.ai's model name as model. For example, if you want to use glm5.2, provider = openai 
    and model = glm5.2. In addition, if you want to use a web api, you need to cp .env.example and 
    provide your own api keys.
    """
    if provider=="openai":
        return init_chat_model(
            model=model,
            model_provider="openai",
            temperature=temperature
        )
    elif provider == "google_genai":
        # Backend selection: this project is set up for Vertex AI (billing-enabled,
        # professor's GCP project), NOT the AI-Studio free-tier Generative Language API.
        # If we don't force this, langchain_google_genai defaults to the Developer API
        # whenever GOOGLE_GENAI_USE_VERTEXAI isn't loaded — which silently burns the
        # 20-requests/day free-tier quota and 429s (RESOURCE_EXHAUSTED / free_tier_requests).
        # Default to Vertex; allow explicit opt-out with GOOGLE_GENAI_USE_VERTEXAI=false.
        use_vertex = os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "true").strip().lower() in ("true", "1", "yes")

        # Accept the various key-name variants used in .env.example / by collaborators.
        api_key = (
            os.getenv("GOOGLE_API_KEY")
            or os.getenv("GEMINI_API_KEY")
            or os.getenv("GOOGLE_CLOUD_API_KEY")
            or os.getenv("GOOGLE_AI_STUDIO_API_KEY")
        )

        kwargs = {
            "model": model,
            "model_provider": "google_genai",
            "temperature": temperature,
        }
        if use_vertex:
            kwargs["vertexai"] = True
            # Two Vertex auth modes:
            #  1. Express mode (API key, an "AQ...." key): works when GOOGLE_API_KEY is in the
            #     environment and NO project/location is passed. This is the professor's setup
            #     (export GOOGLE_API_KEY=... + GOOGLE_GENAI_USE_VERTEXAI=True). No ADC needed.
            #  2. Full Vertex (ADC / service account): used only when GOOGLE_CLOUD_PROJECT is set.
            # langchain_google_genai reads the express-mode key from the GOOGLE_API_KEY env var,
            # so make sure it is populated even if the key was provided under an alias.
            if api_key and not os.getenv("GOOGLE_API_KEY"):
                os.environ["GOOGLE_API_KEY"] = api_key
            project = os.getenv("GOOGLE_CLOUD_PROJECT")
            if project:
                # Full Vertex mode — requires ADC / service-account credentials.
                kwargs["project"] = project
                kwargs["location"] = os.getenv("GOOGLE_CLOUD_LOCATION", "global")
            # else: leave project/location unset so the SDK uses API-key express mode.
        else:
            # Gemini Developer API (API-key) path.
            if api_key:
                kwargs["api_key"] = api_key
        return init_chat_model(**kwargs)
    elif provider == "ollama":
        return init_chat_model(
            model=model,
            model_provider="ollama",
            temperature=temperature
        )
    elif provider == "z.ai":
        return init_chat_model(
            model=model,
            model_provider="openai",
            api_key=os.getenv("ZAI_API_KEY"),
            base_url="https://api.z.ai/api/paas/v4/",
            temperature=temperature,
        )    
    raise ValueError("Unsupported model provider")
    


def invoke_llm(
        model: str,
        provider: str,
        human_messsage: str,
        system_message: Optional[str] = None,
        temperature: float = 0,
) -> str:
    """

    Create an LLM, send it a prompt, and return the model's text response.

    Parameters
    ----------
    model : str
        Model name to use.
    provider : str
        Backend/provider name passed into create_llm().
    human_messsage : str
        The user's task/question/prompt.
        Note: this variable currently has a typo in its name:
        "messsage" instead of "message".
    system_message : str, optional
        Optional instruction that tells the model how to behave.
    temperature : float, optional
        Controls randomness in the model response.

    Returns
    -------
    str
        The content of the model's response message.

    """
    llm = create_llm(provider, model, temperature)

    message = [HumanMessage(human_messsage)]
    if system_message:
        message.append(SystemMessage(system_message))
    
    response = llm.invoke(message)

    return response.content

    

    
    