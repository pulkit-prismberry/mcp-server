# =========================================================
# Multi-stage Dockerfile for Multi-Tenant Support AI MCP Server
# Aligned with support_ai-backend hardened runtime pattern
# =========================================================

# Stage 1: Build virtual environment with dependencies
FROM python:3.11-slim AS builder

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Stage 2: Minimal hardened production runtime
FROM python:3.11-slim AS runner

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH="/app" \
    PATH="/app/.venv/bin:$PATH"

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Run as non-root user for security hardening (matches support_ai-backend)
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -s /bin/sh -d /app appuser

# Copy virtual environment from builder
COPY --from=builder --chown=appuser:appgroup /app/.venv /app/.venv

# Copy MCP server source code
COPY --chown=appuser:appgroup config.py server.py /app/
COPY --chown=appuser:appgroup data /app/data
COPY --chown=appuser:appgroup db /app/db
COPY --chown=appuser:appgroup models /app/models
COPY --chown=appuser:appgroup services /app/services
COPY --chown=appuser:appgroup tools /app/tools
COPY --chown=appuser:appgroup utils /app/utils

USER appuser

CMD ["python", "server.py"]
