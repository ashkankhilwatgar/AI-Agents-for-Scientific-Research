import json
import requests

# Ollama's chat endpoint on the remote server
API_URL = "http://150.209.23.239:11434/api/chat"
MODEL = "qwen2.5:7b"

# Tool definition — describes to Qwen what it can call and what args to pass
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "http_post",
            "description": "Send an HTTP POST request to a URL and return the response body.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The URL to POST to"},
                    "body": {"type": "object", "description": "JSON body to send"},
                },
                "required": ["url", "body"],
            },
        },
    }
]


def execute_tool(name: str, args: dict) -> str:
    """Dispatch a tool call by name and return the result as a string."""
    if name == "http_post":
        resp = requests.post(args["url"], json=args["body"], timeout=60)
        return resp.text
    return f"Unknown tool: {name}"


def run(user_message: str) -> str:
    """
    Agentic loop: send a message, handle any tool calls the model requests,
    and repeat until the model returns a plain text reply.
    """
    messages = [{"role": "user", "content": user_message}]

    while True:
        # Send the full conversation history (plus available tools) to the model
        resp = requests.post(
            API_URL,
            json={"model": MODEL, "messages": messages, "tools": TOOLS, "stream": False},
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        assistant_msg = data["message"]
        # Append the assistant turn so the next request includes it
        messages.append(assistant_msg)

        tool_calls = assistant_msg.get("tool_calls")
        if not tool_calls:
            # No more tool calls — return the final text response
            return assistant_msg.get("content", "")

        # Execute each tool call and feed results back to the model
        for call in tool_calls:
            fn = call["function"]
            result = execute_tool(fn["name"], fn["arguments"])
            print(f"[tool] called {fn['name']} → {result[:200]}")
            # Append the tool result so the model can reason over it
            messages.append({"role": "tool", "content": result})


if __name__ == "__main__":
    reply = run(
        "Use the http_post tool to POST to http://150.209.23.239:11434/api/generate "
        "with body {\"model\": \"qwen2.5:7b\", \"prompt\": \"Say hello!\", \"stream\": false}. "
        "Then tell me what the response said."
    )
    print(f"\n[Qwen final reply]\n{reply}")
