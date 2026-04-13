from fastapi import FastAPI
from pydantic import BaseModel
import httpx
import os

app = FastAPI()

# Ollama endpoint.
# - Local dev default: Ollama on same machine.
# - Railway default: private networking to an `ollama` service in same project.
_default_ollama_url = (
    "http://ollama.railway.internal:11434/api/generate"
    if os.getenv("RAILWAY_ENVIRONMENT_NAME") or os.getenv("RAILWAY_PROJECT_ID")
    else "http://127.0.0.1:11434/api/generate"
)
OLLAMA_URL = (os.getenv("OLLAMA_URL", _default_ollama_url) or "").strip()
if OLLAMA_URL and not OLLAMA_URL.startswith(("http://", "https://")):
    OLLAMA_URL = f"http://{OLLAMA_URL.lstrip('/')}"


class RequestModel(BaseModel):
    prompt: str
    model: str = "qwen2.5:3b"


@app.post("/v1/chat/completions")
async def generate(request: RequestModel):
    payload = {
        "model": request.model,
        "prompt": request.prompt,
        "stream": False
    }

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
            response = await client.post(OLLAMA_URL, json=payload)

        # Handle Ollama errors
        if response.status_code >= 400:
            return {
                "error": "ollama_error",
                "status_code": response.status_code,
                "detail": response.text,
            }

        return response.json()

    except httpx.ConnectError:
        return {
            "error": "ollama_unreachable",
            "detail": f"Cannot connect to Ollama at {OLLAMA_URL}"
        }

    except httpx.ReadTimeout:
        return {
            "error": "ollama_timeout",
            "detail": "Ollama took too long to respond"
        }

    except httpx.HTTPError as e:
        return {
            "error": "ollama_http_error",
            "detail": str(e)
        }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "ollama_url": OLLAMA_URL
    }