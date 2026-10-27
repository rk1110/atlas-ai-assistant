# Build context is the repo root (see docker-compose.yml) so the image can include
# /prompts and /config, which live outside backend/.
FROM python:3.13.17-slim-bookworm

# uv: fast Python package manager. Copied as a single static binary from its official image.
COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /uvx /bin/

# The virtualenv lives outside /app/backend so the dev bind-mount of backend/ doesn't hide it.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

WORKDIR /app/backend

# Dependencies first: this layer is cached until pyproject.toml / uv.lock change.
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-install-project

COPY backend/ ./
COPY prompts/ /app/prompts/
COPY config/ /app/config/

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
