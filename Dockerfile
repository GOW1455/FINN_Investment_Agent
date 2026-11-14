# One image: build the frontend, then serve it and the API from FastAPI.
FROM node:20-slim AS web
WORKDIR /web
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev
COPY backend/ ./
COPY --from=web /web/dist /app/frontend/dist
ENV PORT=8000
CMD ["sh", "-c", "uv run --no-dev uvicorn finn.api:app --host 0.0.0.0 --port ${PORT}"]
