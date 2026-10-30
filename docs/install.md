# Install (Docker + Traefik)

Deployment uses Docker Compose behind an existing Traefik. The app has no published host ports.

## Prerequisites

- Docker with the Compose plugin.
- An external Docker network named `traefik`, created with an explicit subnet:

    ```bash
    docker network create --subnet 172.30.0.0/16 traefik
    ```

    `FORWARDED_ALLOW_IPS` must match this subnet, because it controls which proxy addresses uvicorn trusts for `X-Forwarded-*` headers.
- Traefik attached to that network, with a certificate resolver named `letsencrypt`. The compose example has a commented minimal Traefik service if you do not run one.
- A DNS name for the app (the examples use `hoarder.example.com`) and, optionally, an [OIDC provider](authentik.md) (local admin login works without one).

## Secrets

None to prepare. The master key and session secret are generated into `/data/secrets/` on first start (the container user owns `/data`). Back up the `ih_data` volume: losing `/data/secrets/master_key` makes stored credentials unreadable. `IH_MASTER_KEY[_FILE]` and `IH_SESSION_SECRET[_FILE]` override the generated values.

## Locked out?

Set `IH_BREAK_GLASS=true` and restart to force local login on even if it was disabled or OIDC is broken. Add `IH_BREAK_GLASS_RESET=true` to also reset the local admin: on startup a one-time reset token is written to the log (WARNING `BREAK GLASS RESET token`); enter it with the new password on `/setup`. The token works once per process and changes on every restart. Resetting signs out all existing sessions. Remove both variables afterwards. Recovery writes the new password to the account and to the legacy `local_admin` setting, so it works before and after the local-users migration.

1. Copy [`compose.example.yml`](https://github.com/metril/immich-hoarder/blob/main/compose.example.yml) anywhere you like.
2. Replace `hoarder.example.com` in the Traefik `Host` rule. OIDC and the public URL are configured in the web UI, not in the environment: on first start open the site, create the local admin on `/setup`, then use Settings → Auth.
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

Downloads land in the `/scratch` tmpfs. Its `size=` in the compose file (default 4 GiB) bounds scratch use; if you set the admin `job_scratch_max_bytes` setting, keep it not above the tmpfs size.

## Upgrade

```bash
docker compose pull && docker compose up -d
```

Database migrations run automatically on start. Back up first; see [backups](backups.md).

All settings are listed in the [configuration reference](reference/configuration.md).
