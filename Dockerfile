# syntax=docker/dockerfile:1

# Image for deploying the sections app to Google Cloud Run.

# ---------------------------------------------------------------------------
# Frontend build stage
#
# Type-checks and builds the React app with Vite; Flask serves the output as
# its static and template folder (server/static).
# ---------------------------------------------------------------------------
FROM node:24-slim AS frontend

WORKDIR /build
COPY package.json yarn.lock ./
RUN yarn install --frozen-lockfile

COPY index.html tsconfig.json vite.config.ts ./
COPY public ./public
COPY src ./src
RUN yarn typecheck && yarn build

# ---------------------------------------------------------------------------
# Python build stage
#
# Installs the Python dependencies into a venv that is copied into the
# runtime stage, so pip and its build cache stay out of the shipped image.
# ---------------------------------------------------------------------------
FROM python:3.14-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copied on its own so the dependency layer is only rebuilt when the pins change.
COPY server/requirements.txt ./
RUN pip install -r requirements.txt

# ---------------------------------------------------------------------------
# Runtime stage
# ---------------------------------------------------------------------------
FROM python:3.14-slim

RUN useradd --create-home --uid 1000 app

COPY --from=builder /opt/venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080

WORKDIR /app
COPY --chown=app:app server/ .
COPY --from=frontend --chown=app:app /build/build ./static

USER app

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c 'import os, urllib.request; urllib.request.urlopen("http://127.0.0.1:" + os.environ.get("PORT", "8080") + "/health")'

# With RUN_MIGRATIONS=true (set on staging and production, never on PR previews,
# which share the staging database), apply database migrations before starting.
# `exec` keeps gunicorn as PID 1 so it gets SIGTERM directly on redeploy.
# One worker process with threads, as in seating: Cloud Run's default instance is 1 vCPU.
CMD ["sh", "-c", "if [ \"$RUN_MIGRATIONS\" = true ]; then flask --app main db upgrade || exit 1; fi; exec gunicorn -b 0.0.0.0:${PORT:-8080} main:app --workers ${WEB_CONCURRENCY:-1} --threads ${GUNICORN_THREADS:-8} --timeout ${GUNICORN_TIMEOUT:-120} --access-logfile -"]
