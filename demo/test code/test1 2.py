from pathlib import Path

import requests

API_URL = "http://150.209.23.239:11434/api/generate"
FILE_TO_SEND = "e.txt"
FIRST_MODEL = "qwen2.5:7b"
SECOND_MODEL = "qwen2.5:72b"


def call_llm(model: str, prompt: str) -> str:
    response = requests.post(
        API_URL,
        json={"model": model, "prompt": prompt, "stream": False},
        timeout=6000,
    )
    response.raise_for_status()
    data = response.json()
    return data.get("response", "")


def main() -> None:
    file_text = Path(FILE_TO_SEND).read_text(encoding="utf-8")

    first_prompt = (
        "You are LLM #1. Read the file content and follow the instructions.\n\n"
        f"File path: {FILE_TO_SEND}\n"
        "File content:\n"
        f"{file_text}"
    )
    first_result = call_llm(FIRST_MODEL, first_prompt)

    second_prompt = (
        "You are LLM #2. You received a file and another LLM summary. "
        "Check whether the summary matches the file, then provide a corrected summary if needed.\n\n"
        f"File path: {FILE_TO_SEND}\n"
        "File content:\n"
        f"{file_text}\n\n"
        "LLM #1 summary:\n"
        f"{first_result}"
    )
    second_result = call_llm(SECOND_MODEL, second_prompt)

    print(f"[{FIRST_MODEL}]\n{first_result}\n")
    print(f"[{SECOND_MODEL}]\n{second_result}\n")


if __name__ == "__main__":
    main()