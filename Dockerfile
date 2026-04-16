FROM python:3.11

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Environment defaults (safe for Railway + Docker)
ENV PYTHONUNBUFFERED=1
ENV OLLAMA_URL=http://ollama:11434/api/generate

# Start FastAPI (Railway compatible)
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]