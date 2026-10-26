FROM node:26.11.1-alpine@sha256:143494b1da2945f061539253adc65e4f1569ddf07da2d384c022c791a9d90a4a AS web
WORKDIR /web
# Node 26 no longer bundles corepack: install pnpm from the registry tarball and fail closed
# unless its sha512 matches package.json "packageManager" (keep PNPM_SHA512 in sync).
ARG PNPM_VERSION=12.12.1
ARG PNPM_SHA512=b7f98934c0b1f29a65f5da52f2d7f994e7faad573ffdddea1497fb4dcb5aec051590ee7c7d95a38172b4bfae103a5b83edf2ee866e11731c2cafa96063610ac5
RUN wget -q -O /tmp/pnpm.tgz "https://registry.npmjs.org/pnpm/-/pnpm-${PNPM_VERSION}.tgz" \
    && echo "${PNPM_SHA512}  /tmp/pnpm.tgz" | sha512sum -c - \
    && npm i -g /tmp/pnpm.tgz && rm /tmp/pnpm.tgz
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/.npmrc ./
RUN --mount=type=cache,target=/root/.local/share/pnpm/store pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm build

FROM ghcr.io/astral-sh/uv:0.13.5@sha256:32a7bb39b496babbd997b0a39a4d66c126bdaf5661b302bf6f06abda8deca6ff AS uv

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
COPY --from=web /web/dist /srv/web
WORKDIR /srv/backend
USER 10001
VOLUME /data
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=3).status == 200 else 1)"]
CMD ["python", "-m", "app"]
