from config import (
    PLAN_AGENT_PROVIDER, PLAN_AGENT_MODEL, 
    PLAN_AGENT_TEMPERATURE, TASK_AGENT_PROVIDER, 
    TASK_AGENT_MODEL, TASK_AGENT_TEMPERATURE, 
    DEBUG_AGENT_PROVIDER, DEBUG_AGENT_MODEL, 
    DEBUG_AGENT_TEMPERATURE, JUDGE_AGENT_PROVIDER,
    JUDGE_AGENT_MODEL, JUDGE_AGENT_TEMPERATURE,
    CHECK_AGENT_PROVIDER, CHECK_AGENT_MODEL,
    CHECK_AGENT_TEMPERATURE)

# from demo.config import MAX_RETRY

from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, SystemMessage

from typing import Optional

import threading
_LLM_LOCK = threading.Lock()



model_info = {
    "plan_agent": {
        "provider": PLAN_AGENT_PROVIDER,
        "model": PLAN_AGENT_MODEL,
        "temperature": PLAN_AGENT_TEMPERATURE
    },
    "task_agent": {
        "provider": TASK_AGENT_PROVIDER,
        "model": TASK_AGENT_MODEL,
        "temperature": TASK_AGENT_TEMPERATURE
    },
    "debug_agent": {
        "provider": DEBUG_AGENT_PROVIDER,
        "model": DEBUG_AGENT_MODEL,
        "temperature": DEBUG_AGENT_TEMPERATURE
    },
    "judge_agent": {
        "provider": JUDGE_AGENT_PROVIDER,
        "model": JUDGE_AGENT_MODEL,
        "temperature": JUDGE_AGENT_TEMPERATURE
    },
    "check_agent": {
        "provider": CHECK_AGENT_PROVIDER,
        "model": CHECK_AGENT_MODEL,
        "temperature": CHECK_AGENT_TEMPERATURE
    }
}



def create_agent(agent_name: str):
    """
    Create a LangChain chat model for one agent.
    Supported providers:
        - ollama: use LangChain ChatOllama
        - openai: use LangChain ChatOpenAI
        - google: use LangChain ChatGoogleGenerativeAI
    """
    agent_name = agent_name.lower().strip()
    provider = model_info[agent_name]["provider"].lower().strip()
    model = model_info[agent_name]["model"].lower().strip()
    temperature = model_info[agent_name]["temperature"]

    if provider == "openai":
        return ChatOpenAI(
                model=model,
                temperature=temperature
        )
    elif provider == "google":
        return ChatGoogleGenerativeAI(
            model = model,
            temperature = temperature
        )
    elif provider == "ollama":
        return ChatOllama(
            model = model,
            temperature=temperature
        )
    else:
        raise ValueError(
            "Unrecognized llm provider"
        )
    



def invoke_llm(
        agent_name: str,
        prompt: str,
        system_prompt: Optional[str] = None
) -> str:
    """
    Main shared LLM entry point for all agents.
    Example:
        call_agent_llm("check_agent", prompt)
        call_agent_llm("debug_agent", prompt)
        call_agent_llm("judge_agent", prompt)
        call_agent_llm("plan_agent", prompt)
    """
    agent = create_agent(agent_name)
    message = [HumanMessage(content=prompt)]
    if system_prompt:
        message.append(SystemMessage(content=system_prompt))
    with _LLM_LOCK:
        response = agent.invoke(message)

    return response.content

    

    
    