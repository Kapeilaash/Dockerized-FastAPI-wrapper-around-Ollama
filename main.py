import asyncio
import os
import time

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from usage_db import RequestLogRow, get_sqlite_path, init_db, log_request, usage_summary

app = FastAPI()
SQLITE_PATH = get_sqlite_path()
init_db(SQLITE_PATH)

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

# Read/connect timeout for Ollama (seconds). Tune via env if Railway or the model is slow.
OLLAMA_TIMEOUT_SEC = float(os.getenv("OLLAMA_TIMEOUT_SEC", "600"))
# Total attempts on read timeout (first load of a model can exceed one timeout window).
OLLAMA_MAX_ATTEMPTS = max(1, int(os.getenv("OLLAMA_MAX_ATTEMPTS", "2")))


class RequestModel(BaseModel):
    prompt: str
    model: str = "qwen2.5:3b"


@app.post("/v1/chat/completions")
async def generate(request: RequestModel, http_request: Request):
    http_request.state.model = request.model
    payload = {
        "model": request.model,
        "prompt": request.prompt,
        "stream": False
    }

    timeout = httpx.Timeout(OLLAMA_TIMEOUT_SEC)

    for attempt in range(OLLAMA_MAX_ATTEMPTS):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(OLLAMA_URL, json=payload)

            if response.status_code >= 400:
                return JSONResponse(
                    status_code=502,
                    content={
                        "error": "ollama_error",
                        "status_code": response.status_code,
                        "detail": response.text,
                    },
                )

            return response.json()

        except httpx.ConnectError:
            http_request.state.error_type = "ollama_unreachable"
            return JSONResponse(
                status_code=503,
                content={
                    "error": "ollama_unreachable",
                    "detail": f"Cannot connect to Ollama at {OLLAMA_URL}",
                },
            )

        except httpx.ReadTimeout:
            if attempt + 1 < OLLAMA_MAX_ATTEMPTS:
                await asyncio.sleep(2)
                continue
            http_request.state.error_type = "ollama_timeout"
            return JSONResponse(
                status_code=504,
                content={
                    "error": "ollama_timeout",
                    "detail": (
                        "Ollama took too long to respond. "
                        "Try OLLAMA_TIMEOUT_SEC, a smaller model, or more CPU/RAM on the Ollama service."
                    ),
                },
            )

        except httpx.HTTPError as e:
            http_request.state.error_type = "ollama_http_error"
            return JSONResponse(
                status_code=502,
                content={"error": "ollama_http_error", "detail": str(e)},
            )

    raise RuntimeError("unreachable: Ollama handler should return or raise")


@app.get("/health")
def health():
    return {
        "status": "ok",
        "ollama_url": OLLAMA_URL
    }


@app.middleware("http")
async def usage_logger(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = int((time.perf_counter() - start) * 1000)

    try:
        log_request(
            SQLITE_PATH,
            RequestLogRow(
                method=request.method,
                path=request.url.path,
                status_code=getattr(response, "status_code", 0) or 0,
                duration_ms=duration_ms,
                model=getattr(request.state, "model", None),
                error_type=getattr(request.state, "error_type", None),
            ),
        )
    except Exception:
        # Never break the API if logging fails
        pass

    return response


@app.get("/usage/summary")
def get_usage_summary(since_seconds: int | None = None, limit_paths: int = 20):
    return usage_summary(SQLITE_PATH, since_seconds=since_seconds, limit_paths=limit_paths)