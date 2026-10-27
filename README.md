# immich-hoarder

immich-hoarder fetches images from sites supported by [gallery-dl](https://github.com/mikf/gallery-dl) and uploads them to your [Immich](https://immich.app) server. Add a source URL, pick a target and a schedule, and it keeps your library up to date, skipping what you already have. It ships as a single container with a web UI.

## Features

- gallery-dl sources: any site gallery-dl supports, images only
- Schedules (cron) and backfill modes (full, last N, since a date)
- Per-target dedupe with SHA-1 and perceptual hash (pHash), so duplicates are linked, not re-uploaded
- Albums from templates such as `Reddit/{subreddit}`, plus descriptions from post metadata
- Filters: size, aspect ratio, title regex, date range and more
- OIDC sign-in, scoped API keys and per-resource sharing
- Live job telemetry: dashboard, per-job log viewer and item results
- Notifications via Apprise (global or per source)
- Proxy support, including a gluetun VPN override
- Backups (SQLite snapshots, config export/import) and an optional PostgreSQL database

![Dashboard](docs/assets/screenshots/dashboard-dark.png)

![Job detail](docs/assets/screenshots/job-detail-light.png)

## Quickstart

Image: `ghcr.io/metril/immich-hoarder`. You need Docker with Compose, an external `traefik` network, and, optionally, an OIDC provider (details in the [install guide](https://metril.github.io/immich-hoarder/install/)).

```bash
# 1. get the compose file and set your hostname in it
curl -fsSLO https://raw.githubusercontent.com/metril/immich-hoarder/main/compose.example.yml
# 2. start (no env needed: secrets are generated into the data volume)
docker compose -f compose.example.yml up -d
# 3. open https://hoarder.example.com (your hostname) and create the local admin on the /setup page
# 4. optional: configure OIDC under Settings, then test it and sign in with it
```

## Configuration and recovery

All app configuration (OIDC, public URL, groups, local admin) lives in the web UI. Optional env: `IH_DATABASE_URL`, `IH_LOG_LEVEL`, `FORWARDED_ALLOW_IPS`, and `IH_MASTER_KEY[_FILE]` / `IH_SESSION_SECRET[_FILE]` overrides.

- The master key and session secret are generated into `/data/secrets/` on first start. Back up the `/data` volume: losing `/data/secrets/master_key` makes stored credentials unreadable.
- Upgrading from env-based OIDC: `IH_OIDC_*` / `IH_PUBLIC_URL` are imported into the database once on startup (with a deprecation warning); remove them afterwards.
- Locked out? Set `IH_BREAK_GLASS=true` (plus `IH_BREAK_GLASS_RESET=true` to reset an existing local admin) and restart: local login is forced on and `/setup` is reachable. A banner is shown while it is set; remove the variable and restart to turn it off.

## Documentation

- [Documentation site](https://metril.github.io/immich-hoarder/)
- API reference: `/api/docs` on your instance
- [Contributing](CONTRIBUTING.md)

## License

Proprietary. All rights reserved; the source is visible for reference only. See [LICENSE](LICENSE).
