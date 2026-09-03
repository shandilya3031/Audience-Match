# syntax=docker/dockerfile:1
FROM python:3.13-slim AS builder
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends gcc g++ && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
# CPU-only torch first -- the default Linux wheel pulls in the full NVIDIA
# CUDA toolkit (2GB+) as dependencies, which is dead weight here: Groq
# handles all LLM inference remotely, the only local model is the CPU-run
# sentence-transformers embedding model. Installing the CPU wheel first means
# the plain `pip install -r requirements.txt` below is already satisfied for
# torch and won't reach for the GPU variant.
#
# --mount=type=cache on pip's own cache dir (not --no-cache-dir) so
# downloaded wheels persist across separate `docker build` invocations --
# these are large, slow downloads on a constrained connection and a rebuild
# shouldn't have to re-fetch what it already fetched.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install torch --index-url https://download.pytorch.org/whl/cpu
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

FROM python:3.13-slim AS production
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
COPY --from=builder /usr/local/lib/python3.13 /usr/local/lib/python3.13
COPY . .
RUN useradd -m appuser
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --retries=3 CMD curl -f http://localhost:8000/health || exit 1
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
