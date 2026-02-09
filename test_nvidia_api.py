import requests
import os
import json

api_key = os.environ.get("NVIDIA_API_KEY")
if not api_key:
    print("Error: NVIDIA_API_KEY not set")
    exit(1)

invoke_url = "https://integrate.api.nvidia.com/v1/chat/completions"
stream = False

headers = {
  "Authorization": f"Bearer {api_key}",
  "Accept": "text/event-stream" if stream else "application/json"
}

payload = {
  "model": "moonshotai/kimi-k2.5",
  "messages": [{"role":"user","content":"Which number is larger, 9.11 or 9.8?"}],
  "max_tokens": 1024,
  "temperature": 0.20,
  "top_p": 1.00,
  "stream": stream,
  "chat_template_kwargs": {"thinking":False},
}

try:
    response = requests.post(invoke_url, headers=headers, json=payload)
    response.raise_for_status()
    print(json.dumps(response.json(), indent=2))
except Exception as e:
    print(f"Error: {e}")
    if 'response' in locals():
        print(response.text)
