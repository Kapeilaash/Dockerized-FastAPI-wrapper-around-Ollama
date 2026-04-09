import time
import requests

url = "http://127.0.0.1:8000/v1/chat/completions"   # IMPORTANT

prompts = [
    "What is AI?",
    "Explain Machine Learning",
    "What is Deep Learning?"
]

for prompt in prompts:
    start_time = time.time()

    response = requests.post(url, json={
        "prompt": prompt,
        "model": "qwen2.5:3b"
    })

    end_time = time.time()

    print("\n====================")
    print("Prompt:", prompt)
    print("Response:", response.json())
    print("Latency:", round(end_time - start_time, 2), "seconds")