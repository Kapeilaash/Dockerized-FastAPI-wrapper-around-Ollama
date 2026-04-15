## FastAPI wrapper for Ollama

This project exposes an **OpenAI-style** endpoint (`/v1/chat/completions`) backed by **Ollama**, plus a simple health check (`/health`).

If enabled in your `main.py`, it also logs request stats to SQLite and exposes a usage summary endpoint (`/usage/summary`).

## Requirements

- **Python 3.11+** (you’re using Python 3.13 on Windows, which is fine)
- Ollama running locally or reachable over HTTP

## Setup

Create and activate a virtual environment, then install dependencies:

```bash
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

If you don’t have a `requirements.txt` yet, install at least:

```bash
pip install fastapi uvicorn httpx pydantic
```

## Run the API (dev)

```bash
uvicorn main:app --reload
```

By default the server runs at:

- `http://127.0.0.1:8000`
- Swagger UI: `http://127.0.0.1:8000/docs`

## Run with Docker

This repo includes a `Dockerfile` and `docker-compose.yml` that can run **both** the FastAPI app and an Ollama container.

### Option A: Docker Compose (recommended)

Build and start everything:

```bash
docker compose up --build
```

Then open:

- API: `http://127.0.0.1:8000`
- Docs: `http://127.0.0.1:8000/docs`

Ollama is exposed at `http://127.0.0.1:11434`.

### Option B: Docker only (FastAPI container)

Build:

```bash
docker build -t fastapi-ollama-wrapper .
```

Run (you must point `OLLAMA_URL` to an Ollama that the container can reach):

```bash
docker run --rm -p 8000:8000 ^
  -e OLLAMA_URL="http://host.docker.internal:11434/api/generate" ^
  fastapi-ollama-wrapper
```

Notes:

- On Windows/macOS, `host.docker.internal` usually works to reach an Ollama running on your host.
- On Linux, you may need `--network=host` (or run Ollama in another container and use a Docker network).

## Railway (hosted)

If you deploy this API to Railway, you can call the same endpoints using your Railway public URL.

### Example request (Railway)

```bash
curl -X POST "https://amused-reverence-dev.up.railway.app/v1/chat/completions" ^
  -H "Content-Type: application/json" ^
  -d "{\"prompt\":\"Hello\",\"model\":\"qwen2.5:3b\"}"
```

### Railway environment variables

- `PORT`: Railway sets this automatically (the `Dockerfile` uses it).
- `OLLAMA_URL`: set this to wherever Ollama is reachable from Railway (for example, an Ollama server/VPS you run, or another hosted endpoint).

## Configuration

### Ollama URL

The API forwards requests to Ollama using `OLLAMA_URL` from `main.py`. If your code supports an environment variable, you can set it like this:

```bash
# Windows PowerShell example
$env:OLLAMA_URL="http://127.0.0.1:11434/api/generate"
uvicorn main:app --reload
```

## Endpoints

### `POST /v1/chat/completions`

Example request:

```bash
curl -X POST http://127.0.0.1:8000/v1/chat/completions ^
  -H "Content-Type: application/json" ^
  -d "{\"model\":\"llama3\",\"prompt\":\"Say hello\"}"
```

### `GET /health`

```bash
curl http://127.0.0.1:8000/health
```

### `GET /usage/summary` (optional)

If your current `main.py` includes the usage middleware + endpoint, you can query aggregated request stats from SQLite.

- All time:

```bash
curl http://127.0.0.1:8000/usage/summary
```

- Last 1 hour:

```bash
curl "http://127.0.0.1:8000/usage/summary?since_seconds=3600"
```

- Limit number of returned “top paths”:

```bash
curl "http://127.0.0.1:8000/usage/summary?limit_paths=10"
```

## Notes for Git / Windows line endings

If you see a warning like “LF will be replaced by CRLF”, add a `.gitattributes` to keep consistent line endings in the repo:

```gitattributes
* text=auto
*.py text eol=lf
```
