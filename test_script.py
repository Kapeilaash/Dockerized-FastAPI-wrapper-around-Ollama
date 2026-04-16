import time
import requests

# -----------------------------
# API ENDPOINT
# -----------------------------
URL = "http://127.0.0.1:8000/v1/chat/completions"

# -----------------------------
# TEST PROMPTS
# -----------------------------
prompts = [
    "What is Artificial Intelligence?",
    "Explain Machine Learning in simple terms",
    "What is Deep Learning and how is it different from ML?"
]

# -----------------------------
# STORE LATENCIES
# -----------------------------
latencies = []

# -----------------------------
# SEND REQUESTS
# -----------------------------
for i, prompt in enumerate(prompts, start=1):
    print("\n" + "=" * 40)
    print(f"Request {i}")
    print("Prompt:", prompt)

    start_time = time.time()

    response = requests.post(
        URL,
        json={
            "prompt": prompt,
            "model": "qwen2.5:0.5b"   # ✅ FIXED MODEL
        }
    )

    end_time = time.time()
    latency = round(end_time - start_time, 3)
    latencies.append(latency)

    # -----------------------------
    # HANDLE RESPONSE
    # -----------------------------
    try:
        data = response.json()
    except Exception:
        data = response.text

    print("\nResponse:")
    print(data)

    print(f"\nLatency: {latency} seconds")

# -----------------------------
# FINAL SUMMARY
# -----------------------------
print("\n" + "=" * 40)
print("📊 PERFORMANCE SUMMARY")
print("=" * 40)

print(f"Total Requests: {len(prompts)}")
print(f"Average Latency: {sum(latencies)/len(latencies):.3f} seconds")
print(f"Min Latency: {min(latencies):.3f} seconds")
print(f"Max Latency: {max(latencies):.3f} seconds")