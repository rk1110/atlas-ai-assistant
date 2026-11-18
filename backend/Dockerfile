# Build context is the repo root (see docker-compose.yml) so the image can include
# /prompts and /config, which live outside backend/.
#
# Two targets (Phase 7D):
#   dev   runs as root; docker-compose.yml bind-mounts backend/ over it and adds --reload
#   prod  the same files, run as an unprivileged user; docker-compose.prod.yml
FROM python:3.13.17-slim-bookworm AS dev

# uv: fast Python package manager. Copied as a single static binary from its official image.
COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /uvx /bin/

# The virtualenv lives outside /app/backend so the dev bind-mount of backend/ doesn't hide it.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_HTTP_TIMEOUT=300 \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

WORKDIR /app/backend

# Dependencies first: this layer is cached until pyproject.toml / uv.lock change.
# The cache mount keeps uv's download cache between builds, so changing one dependency
# re-downloads only that package instead of all ~85 (the first build still fetches everything).
COPY backend/pyproject.toml backend/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project

COPY backend/ ./
COPY prompts/ /app/prompts/
COPY config/ /app/config/

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

# ---------------------------------------------------------------------------- prod
FROM dev AS prod
# Unprivileged user: a bug in the app can't modify the code or the virtualenv. Models from
# Hugging Face (embeddings, reranker, Whisper) are cached in its home, on a volume.
RUN useradd --create-home --uid 10001 atlas \
    && mkdir -p /home/atlas/.cache/huggingface /app/uploads \
    && chown -R atlas:atlas /home/atlas/.cache /app/uploads
# (A new named volume copies these folders' owner, so the user can write to it.)
ENV HF_HOME=/home/atlas/.cache/huggingface
USER atlas
# --proxy-headers: behind an HTTPS load balancer, trust its X-Forwarded-* headers so the app
# knows requests arrived over HTTPS. One worker: each loads the embedding model (~0.5 GB);
# scale with more containers instead.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
