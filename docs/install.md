# Install (Iris + Traefik)

Deployment uses Docker Compose behind an existing Traefik. The app has no published host ports.

## Prerequisites

- Docker with the Compose plugin.
- An external Docker network named `traefik`, created with an explicit subnet:

    ```bash
    docker network create --subnet 172.30.0.0/16 traefik
    ```

    `FORWARDED_ALLOW_IPS` must match this subnet, because it controls which proxy addresses uvicorn trusts for `X-Forwarded-*` headers.
- Traefik attached to that network, with a certificate resolver named `letsencrypt`. The compose example has a commented minimal Traefik service if you do not run one.
- A DNS name for the app (the examples use `hoarder.example.com`) and an [OIDC provider](authentik.md).

## Secrets

```bash
mkdir secrets
openssl rand -base64 48 > secrets/ih_master_key
openssl rand -base64 48 > secrets/ih_session_secret
# paste the OIDC client secret from your provider
install -m 600 /dev/stdin secrets/ih_oidc_client_secret
sudo chown 10001:10001 secrets/* && chmod 600 secrets/*
```

The container runs as uid 10001, so the secret files must be readable by that uid.

The master key encrypts stored credentials and must be high-entropy; see [security](security.md). Losing it makes stored credentials unreadable.

## Deploy

1. Copy [`compose.example.yml`](https://github.com/metril/immich-hoarder/blob/main/compose.example.yml) next to your `secrets/` directory.
2. Replace `hoarder.example.com` (in `IH_PUBLIC_URL` and the Traefik `Host` rule) and the OIDC issuer. Set `IH_OIDC_CLIENT_ID` to the client ID that Authentik shows for your provider, not the example value `immich-hoarder`.
3. Start it:

    ```bash
    docker compose up -d
    ```

4. Check health through Traefik:

    ```bash
    curl -fsS https://hoarder.example.com/healthz
    curl -fsS https://hoarder.example.com/readyz
    ```

    `/healthz` reports the process is up; `/readyz` also checks the database.

Optional overrides, used with `-f compose.example.yml -f <file>`:

- [`deploy/compose.postgres.yml`](https://github.com/metril/immich-hoarder/blob/main/deploy/compose.postgres.yml): PostgreSQL instead of SQLite.
- [`deploy/compose.gluetun.yml`](https://github.com/metril/immich-hoarder/blob/main/deploy/compose.gluetun.yml): route egress through a gluetun VPN container.

## Scratch space

Downloads land in the `/scratch` tmpfs. Its `size=` in the compose file and `IH_SCRATCH_MAX_BYTES` (default 4 GiB, `4294967296`) must agree: if you change one, change the other, keeping the byte limit not above the tmpfs size.

## Upgrade

```bash
docker compose pull && docker compose up -d
```

Database migrations run automatically on start. Back up first; see [backups](backups.md).

All settings are listed in the [configuration reference](reference/configuration.md).
