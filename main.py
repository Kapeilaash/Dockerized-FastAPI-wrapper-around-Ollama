from fastapi import FastAPI
from pydantic import BaseModel
import httpx
import os

app = FastAPI()

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")


class RequestModel(BaseModel):
    prompt: str
    model: str = "qwen2.5:3b"


@app.post("/v1/chat/completions")
async def generate(request: RequestModel):
    payload = {"model": request.model, "prompt": request.prompt, "stream": False}

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
            response = await client.post(OLLAMA_URL, json=payload)

        # Ollama returns useful error text/json; surface it cleanly.
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
            "detail": f"Ollama is not reachable at {OLLAMA_URL}. Start Ollama (or docker compose), then retry.",
        }
    except httpx.ReadTimeout:
        return {
            "error": "ollama_timeout",
            "detail": "Ollama took too long to respond. Try a smaller prompt/model or retry.",
        }
    except httpx.HTTPError as e:
        return {"error": "ollama_http_error", "detail": str(e)}

@app.get("/health")
def health():
    return {"status": "ok"}        