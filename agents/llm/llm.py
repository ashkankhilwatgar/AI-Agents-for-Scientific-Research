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
        return init_chat_model(
            model=model,
            model_provider="google_genai",
            temperature=temperature
        )
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

    

    
    