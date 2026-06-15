# from google import genai

# client = genai.Client()

# models = [
#     "gemini-3.5-flash",
#     "gemini-3.1-pro-preview",
#     "gemini-2.5-pro",
#     "gemini-2.5-flash",
# ]
# model = models[0]

# response = client.models.generate_content(
#     model=model,
#     contents="Explain what is ACMG/AMP"
# )
# print(response.text)


# import os
# from openai import OpenAI, AuthenticationError

# # Replace with your actual key or load from your environment
# os.environ["OPENAI_API_KEY"] = "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"

# client = OpenAI()

# try:
#     models = client.models.list()
#     print("Success: Your OpenAI API key is valid!")
    
#     print("Available models:")
#     for model in list(models.data):
#         print(f"- {model.id}")
        
# except AuthenticationError:
#     print("Error: Your API key is invalid or has been revoked.")
# except Exception as e:
#     print(f"An unexpected error occurred: {e}")

import requests
response = requests.post(
    "http://150.209.23.239:11434/api/generate", 
    json={
        "model": "qwen2.5:7b",
        "prompt": "Hello, what model are you?",
        "stream": False
    }
)

print(response.json()["response"])