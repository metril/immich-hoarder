# Troubleshooting

## Logs

The app logs one JSON object per line to stderr, so `docker logs` is the place to look:

```bash
docker compose logs -f immich-hoarder
docker compose logs immich-hoarder | jq -c 'select(.level == "error")'
```

Fields are `ts`, `level`, `logger`, `msg` plus any extras; secrets show as `***`. The process level is `IH_LOG_LEVEL` (`error`, `warn`, `info`, `debug`, `trace`). Each job also keeps its own log, visible in the GUI log viewer and at `GET /api/v1/jobs/{id}/events`, and a run can use a more verbose per-run log level (the source's `log_level`, or the level chosen when you press Run).

## Login

### Login returns 503 "OIDC is not configured"

**Cause:** `IH_OIDC_ISSUER`, `IH_OIDC_CLIENT_ID` or the client secret is unset, so login is disabled. **Fix:** set all three (see [Authentik](authentik.md)) and restart.

### Redirect URI mismatch at the provider

**Cause:** the provider's allowed redirect does not match what the app sends, which is `<IH_PUBLIC_URL>/api/v1/auth/callback`. **Fix:** register exactly that URL, with the same scheme and host as `IH_PUBLIC_URL`.

### Login ends with 403 "access denied"

**Cause:** the user is disabled, or none of their groups is in `IH_OIDC_ADMIN_GROUPS` or `IH_OIDC_USER_GROUPS`. **Fix:** add the user to a mapped group and check that the provider sends the groups claim named by `IH_OIDC_GROUPS_CLAIM`. A `401 login failed` means the token exchange failed; check the client secret and issuer.

### Wrong client IP, or redirects go to `http://`

**Cause:** uvicorn does not trust the proxy's `X-Forwarded-*` headers. **Fix:** set `FORWARDED_ALLOW_IPS` to the proxy's address or subnet (see [Install](install.md)) and make sure `IH_PUBLIC_URL` uses `https`.

## Sources

### `private host not allowed` (or `private proxy host not allowed`)

**Cause:** the source URL, or a per-source proxy, resolves to a private, loopback or link-local address. For notifications the message is `private notification host not allowed`. **Fix:** use a public address. If the internal target is intended, an admin can enable `allow_private_hosts`; read [Security](security.md) first, since it applies to every source.

### `unsupported url`

**Cause:** no gallery-dl extractor matches the URL, or it is not a plain `http(s)` URL. **Fix:** check the list at `GET /api/v1/extractors` and use the page URL the site supports.

### A job is stuck, or the scratch space is full

**Cause:** downloads wait while in-flight data exceeds the scratch limit (`IH_SCRATCH_MAX_BYTES`, or the admin's `job_scratch_max_bytes`) or the scratch disk has less than 5% free. If uploads are slow, or `IH_SCRATCH_MAX_BYTES` is larger than the `/scratch` tmpfs, the tmpfs fills first. **Fix:** keep the compose `tmpfs` `size=` and `IH_SCRATCH_MAX_BYTES` in agreement (the limit not above the tmpfs size), check that Immich is accepting uploads, or cancel and retry the job. Leftover job directories are swept at start.

### Items counted as `deleted_in_immich`

**Cause:** the image matches an asset that was deleted or trashed in Immich, so it is deliberately not re-uploaded. **Fix:** nothing is wrong. To bring the image back, restore it from Immich's trash.

### Rate limiting (HTTP 429) and slow runs

**Cause:** the site, or Immich, is throttling. Immich requests retried on 429/502/503/504 with 0.5 s, 1 s and 2 s waits, honoring `Retry-After` up to 10 seconds, then fail as "Immich unavailable (HTTP 429)". Site requests follow the per-site `rate_limits`. **Fix:** raise `sleep_request` and `sleep` for that site in Settings, or lower `upload_concurrency`.

## Immich

### Target test fails

The target **Test** reports one of: `unauthorized` (the API key is wrong), `unreachable` (the URL cannot be reached from the container), or a list of missing permissions. **Fix:** create the Immich API key with permissions `asset.upload`, `asset.read`, `asset.update`, `asset.view`, `album.read`, `album.create`, `albumAsset.create` and `user.read` (or `all`). A running job that gets an authorization error from Immich stops with `immich_unauthorized`.

## Configuration

### Start fails with "must be at least 32 characters"

**Cause:** `IH_MASTER_KEY` or `IH_SESSION_SECRET` is shorter than 32 characters. **Fix:** generate each with `openssl rand -base64 48`. A secret file with a trailing newline is fine, because trailing line breaks are trimmed. If you replace an existing `MASTER_KEY`, stored credentials can no longer be decrypted.

## Live updates

### The dashboard or log does not update

**Cause:** a reverse proxy in front of the app buffers the server-sent event streams (`/api/v1/jobs/stream`, `/api/v1/jobs/{id}/stream`). **Fix:** disable response buffering for `/api/*` (for nginx, `proxy_buffering off;`), and do not enable response compression for `text/event-stream`. Traefik does not buffer by default. Streams send a ping every 15 seconds, so keep proxy idle timeouts above that.
