# API

The interactive OpenAPI docs are served at `/api/docs` on your instance (for example `https://hoarder.example.com/api/docs`), and the schema at `/api/openapi.json`.

## Authentication

Create a key under **API Keys** in the GUI. The full key looks like `ih_<8 chars>_<32 chars>` and is shown once. Send it either way:

```bash
curl -H "X-API-Key: ih_abcd1234_..." https://hoarder.example.com/api/v1/sources
curl -H "Authorization: Bearer ih_abcd1234_..." https://hoarder.example.com/api/v1/sources
```

Keys are stored hashed. They can have an expiry date, and revoking one takes effect immediately. A key can never exceed its creator: the `admin` scope needs an admin, and a key created by another key can only grant scopes that key has. A key acts as its user using the role and groups from that user's last login, and stops working if the user is disabled or loses their groups.

CSRF protection applies only to browser cookie sessions. API-key and bearer-token requests do not need the `X-CSRF-Token` header.

## Scopes

A key can only call endpoints its scopes allow. Admin-only endpoints (`/api/v1/admin/*`, users, settings) need the `admin` scope on an admin's key.

| Scope | Allows |
|---|---|
| `sources:read` | List and read sources, list extractors, preview |
| `sources:write` | Create, edit and delete sources |
| `sources:run` | Run a source, ad-hoc rip, retry a job |
| `targets:read` | List and read targets, test, list albums |
| `targets:write` | Create, edit and delete targets |
| `credentials:read` | List credentials (metadata only) |
| `credentials:write` | Create, edit and delete credentials |
| `jobs:read` | List jobs, items, events, live streams |
| `jobs:write` | Cancel jobs |
| `keys:read` | List API keys |
| `keys:write` | Create and revoke API keys |
| `metrics:read` | Read `/metrics` (Prometheus) |
| `admin` | Admin endpoints (admins only) |

Reading or editing sharing follows the resource's `read` / `write` scope.

## Examples

```bash
H='X-API-Key: ih_abcd1234_...'
B=https://hoarder.example.com/api/v1

# list sources
curl -H "$H" "$B/sources"

# run source 7 now (optionally with a log level); returns 202 and the job
curl -H "$H" -H 'Content-Type: application/json' \
  -d '{"log_level": "debug"}' -X POST "$B/sources/7/run"

# follow a job live (server-sent events)
curl -N -H "$H" "$B/jobs/42/stream"

# read a job's log lines so far (paginated)
curl -H "$H" "$B/jobs/42/events?min_level=warn"
```

`GET /api/v1/jobs/{id}/stream` is the live feed and `GET /api/v1/jobs/{id}/events` is the paginated log; `GET /api/v1/jobs/stream` is the dashboard feed. List endpoints return `{"items": [...], "next_cursor": ...}`; pass `cursor` and `limit` to page.
