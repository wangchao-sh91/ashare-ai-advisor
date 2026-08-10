# syntax=docker/dockerfile:1.7
FROM python:3.12.11-slim-bookworm AS builder

ENV VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install --yes --no-install-recommends build-essential git \
    && rm -rf /var/lib/apt/lists/* \
    && python -m venv "$VIRTUAL_ENV"

WORKDIR /build
COPY pyproject.toml ./
COPY app ./app
RUN python -m pip install --upgrade "pip==25.1.1" \
    && python -m pip install . \
    && test -x /opt/venv/bin/mcp-server-askecho-search-infinity

FROM python:3.12.11-slim-bookworm AS runtime

ENV VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production \
    BIND_MODE=container \
    API_HOST=0.0.0.0 \
    API_PORT=8000

RUN groupadd --system --gid 10001 advisor \
    && useradd --system --uid 10001 --gid advisor --home-dir /nonexistent --shell /usr/sbin/nologin advisor

COPY --from=builder /opt/venv /opt/venv
WORKDIR /app
USER 10001:10001

EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=6 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).read()"]

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log"]
