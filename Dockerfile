# Plan 4 adds a node build stage for the web frontend here.

FROM ghcr.io/astral-sh/uv:0.10.9@sha256:10902f58a1606787602f303954cea099626a4adb02acbac4c69920fe9d278f82 AS uv

FROM python:3.12-slim@sha256:a0f57064cbdcd6285fa45f51237ab0b35ea8ebaed06a1f5973e89e19dfb86704 AS builder
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /build
ENV UV_PROJECT_ENVIRONMENT=/opt/venv UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock README.md LICENSE ./
RUN uv sync --frozen --no-dev --no-editable --no-install-project

FROM python:3.12-slim@sha256:a0f57064cbdcd6285fa45f51237ab0b35ea8ebaed06a1f5973e89e19dfb86704
LABEL org.opencontainers.image.source="https://github.com/metril/immich-hoarder" \
      org.opencontainers.image.licenses="LicenseRef-Proprietary"
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PATH=/opt/venv/bin:$PATH PYTHONPATH=/srv/backend \
    FORWARDED_ALLOW_IPS=127.0.0.1
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin hoarder \
    && mkdir /data /scratch && chown 10001:10001 /data /scratch
COPY --from=builder /opt/venv /opt/venv
# backend/ keeps alembic.ini and alembic/ next to the app package (see app/db/migrate.py)
COPY backend/ /srv/backend/
RUN python -m compileall -q /srv/backend
WORKDIR /srv/backend
USER 10001
VOLUME /data
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=3).status == 200 else 1)"]
CMD ["python", "-m", "app"]
