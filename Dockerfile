# One image, three runtime modes (ui / api / worker) — picked by APP_MODE
# and the docker-compose `command:` for each service.
# See docs/adr/0001-single-image-multi-mode-containers.md.

# ---- stage 1: build the React app ----
FROM node:24-alpine AS frontend-build
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- stage 2: python runtime (api + worker + ui-static-server) ----
FROM python:3.12-slim AS runtime
WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

# Dependency layer first so it's cached independently of app code changes.
COPY backend/pyproject.toml backend/uv.lock backend/README.md ./
RUN uv sync --frozen --no-install-project --no-dev

COPY backend/src ./src
RUN uv sync --frozen --no-dev

# The built React static assets — main.py serves these in `ui` mode.
COPY --from=frontend-build /frontend/dist ./static

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src"

EXPOSE 8000
CMD ["uvicorn", "ticker_backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
