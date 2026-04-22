import asyncio
import base64
import binascii
import os
import time

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, model_validator

from usage_db import RequestLogRow, get_sqlite_path, init_db, log_request, usage_summary

# -----------------------------
# App + DB Init
# -----------------------------
app = FastAPI()

SQLITE_PATH = get_sqlite_path()
init_db(SQLITE_PATH)

# -----------------------------
# Ollama Configuration
# -----------------------------
# Railway → internal service
# Local → localhost
_default_ollama_url = (
    "http://ollama.railway.internal:11434/api/generate"
    if os.getenv("RAILWAY_ENVIRONMENT_NAME") or os.getenv("RAILWAY_PROJECT_ID")
    else "http://127.0.0.1:11434/api/generate"
)

OLLAMA_URL = (os.getenv("OLLAMA_URL", _default_ollama_url) or "").strip()

if OLLAMA_URL and not OLLAMA_URL.startswith(("http://", "https://")):
    OLLAMA_URL = f"http://{OLLAMA_URL.lstrip('/')}"

# Timeout + retry config
OLLAMA_TIMEOUT_SEC = float(os.getenv("OLLAMA_TIMEOUT_SEC", "600"))
OLLAMA_MAX_ATTEMPTS = max(1, int(os.getenv("OLLAMA_MAX_ATTEMPTS", "2")))

# 🔥 FORCE SAFE MODEL
MODEL_NAME = "qwen2.5:0.5b"
DEFAULT_TEMPERATURE = float(os.getenv("OLLAMA_TEMPERATURE", "0.2"))

# -----------------------------
# Request Schema
# -----------------------------
class RequestModel(BaseModel):
    prompt: str | None = Field(default=None, description="Prompt text (JSON strings must escape newlines and quotes).")
    prompt_b64: str | None = Field(
        default=None,
        description="Base64-encoded UTF-8 prompt (recommended for long multiline prompts).",
    )
    temperature: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Sampling temperature (0.0–1.0). If omitted, server default is used.",
    )

    @model_validator(mode="after")
    def _validate_prompt(self):
        if (self.prompt is None or self.prompt == "") and (self.prompt_b64 is None or self.prompt_b64 == ""):
            raise ValueError("Provide either 'prompt' or 'prompt_b64'.")
        return self


def _decode_prompt_b64(prompt_b64: str) -> str:
    try:
        raw = base64.b64decode(prompt_b64, validate=False)
    except (binascii.Error, ValueError) as e:
        raise ValueError(f"Invalid base64 in prompt_b64: {e}") from e
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as e:
        raise ValueError(f"prompt_b64 must decode to UTF-8 text: {e}") from e


def _style_prefix_for_temperature(temperature: float) -> str:
    """
    Map temperature to a response style. This makes the *format/structure* change
    predictably with temperature, instead of relying on randomness alone.
    """
    if temperature <= 0.2:
        return (
            "STYLE:\n"
            "- Be concise and strict.\n"
            "- Use minimal words.\n"
            "- Do not add extra explanations or filler.\n"
            "- If the user asked for a specific output format, output ONLY that.\n"
            "\n"
        )
    if temperature <= 0.7:
        return (
            "STYLE:\n"
            "- Normal level of detail.\n"
            "- Be clear and helpful.\n"
            "- If the user asked for a specific output format, output ONLY that.\n"
            "\n"
        )
    return (
        "STYLE:\n"
        "- More detailed and structured.\n"
        "- Use clear sections/bullets when appropriate.\n"
        "- Still follow the user's required output format if specified.\n"
        "- Avoid repeating the entire prompt.\n"
        "\n"
    )


# -----------------------------
# Chat Endpoint
# -----------------------------
@app.post("/v1/chat/completions")
async def generate(request: RequestModel, http_request: Request):
    start_time = time.perf_counter()

    # Track model for logging
    http_request.state.model = MODEL_NAME

    prompt = request.prompt if request.prompt is not None else _decode_prompt_b64(request.prompt_b64 or "")
    temperature = DEFAULT_TEMPERATURE if request.temperature is None else float(request.temperature)
    styled_prompt = _style_prefix_for_temperature(temperature) + prompt

    payload = {
        "model": MODEL_NAME,
        "prompt": styled_prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
        },
    }

    timeout = httpx.Timeout(OLLAMA_TIMEOUT_SEC)

    for attempt in range(OLLAMA_MAX_ATTEMPTS):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(OLLAMA_URL, json=payload)

            # Ollama error
            if response.status_code >= 400:
                http_request.state.error_type = "ollama_error"
                return JSONResponse(
                    status_code=502,
                    content={
                        "error": "ollama_error",
                        "status_code": response.status_code,
                        "detail": response.text,
                    },
                )

            data = response.json()

            return {
                "model": MODEL_NAME,
                "response": data.get("response"),
                "latency_ms": int((time.perf_counter() - start_time) * 1000)
            }

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
                    "detail": "Ollama took too long to respond."
                },
            )

        except httpx.HTTPError as e:
            http_request.state.error_type = "ollama_http_error"
            return JSONResponse(
                status_code=502,
                content={"error": "ollama_http_error", "detail": str(e)},
            )

    raise RuntimeError("Unreachable state")


# -----------------------------
# Health Check
# -----------------------------
@app.get("/health")
def health():
    return {
        "status": "ok",
        "model": MODEL_NAME,
        "ollama_url": OLLAMA_URL
    }


# -----------------------------
# Logging Middleware
# -----------------------------
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
        # Never break API due to logging failure
        pass

    return response


# -----------------------------
# Usage Summary Endpoint
# -----------------------------
@app.get("/usage/summary")
def get_usage_summary(since_seconds: int | None = None, limit_paths: int = 20):
    return usage_summary(
        SQLITE_PATH,
        since_seconds=since_seconds,
        limit_paths=limit_paths
    )