# Security notes

API-key requests use the role and groups from the user's last login or bearer-token use. Roles come only from OIDC groups and are refreshed on each login or bearer use. Disabling a user takes effect immediately, including for their API keys.

`MASTER_KEY` must be high-entropy (32+ random characters, e.g. `openssl rand -base64 48`). Encryption keys are derived with HKDF, which is not a password KDF and gives no protection to a guessable passphrase.

A missing target or credential returns 403, not 404, so the API does not reveal whether an id exists to callers who cannot access it.

User notification URLs (apprise credentials) are blocked from connecting to private addresses at resolve time, so a private `HTTP(S)_PROXY` environment variable also blocks those gated sends. Admin-configured global notification URLs are unaffected.

## Residual risks (accepted)

- DNS and proxy-target SSRF: the connect guard vets the addresses the host resolves to, but what an admin-configured proxy then connects to is the proxy's responsibility. Restrict the proxy's own egress.
- `allow_private_hosts` (admin rip setting) disables the private-address guard for downloads. Enable it only on trusted networks; it applies to every source.
- The scratch soft cap can be overshot by the files already in flight when it is reached, and two concurrent near-duplicates of the same image can both be uploaded because neither is recorded yet when the other is checked.

## Secrets and keys

- **`MASTER_KEY` entropy.** Use at least 32 random characters, for example `openssl rand -base64 48`. Encryption keys are derived with HKDF, which is not a password KDF, so a guessable passphrase gets no protection. Values shorter than 32 characters are rejected at start.
- **Losing `MASTER_KEY` makes stored credentials unrecoverable**: site credentials, Immich API keys and notification URLs cannot be decrypted, and encrypted config exports cannot be imported. Back it up separately from the database. Changing it has the same effect.
- Secrets can be supplied as files (`IH_MASTER_KEY_FILE`, `IH_SESSION_SECRET_FILE`, `IH_OIDC_CLIENT_SECRET_FILE`, `IH_DATABASE_URL_FILE`) so they stay out of the process environment.

## Private addresses and SSRF

Downloads are guarded against private, loopback, link-local and similar addresses: the URL is checked when a source is saved, and the connection is checked again at connect time against what the host resolves to.

- **`allow_private_hosts`** (admin rip setting, off by default) turns that guard off for downloads, and also allows private per-source proxies and private notification URLs. It applies to every source on the instance, so enable it only on a trusted network.
- **Notification URLs:** the private-host check applies to per-source (user) notification URLs. Admin-configured global notification URLs are exempt.
- **Proxy environment variables:** gated notification sends resolve through the same guard, so a private `HTTP_PROXY` / `HTTPS_PROXY` set on the container blocks them.
- **DNS and proxy residuals:** see below.

## Hardening in the default compose file

The container runs as uid 10001 with `read_only: true`, `cap_drop: ALL` and `no-new-privileges`. The only writable places are the `/data` volume, the `/scratch` tmpfs for downloads and a `/tmp` tmpfs. No host ports are published; Traefik terminates TLS.

## Logging

Logs are JSON on stderr. Secrets are masked as `***`: values under keys that look sensitive (password, token, secret, key, authorization, cookie, credential), URL userinfo (`https://user:pass@host`), sensitive query parameters (`?token=...`), `Bearer` and `X-API-Key` values, and `ih_...` API keys. Job logs and notifications are also scrubbed of the job's credentials.

## Proxies and sessions

- **Trusted proxies:** set `FORWARDED_ALLOW_IPS` to the reverse proxy's address or subnet (the compose file uses the Traefik network's subnet). Only those addresses may set `X-Forwarded-*`; the default `127.0.0.1` trusts nobody else.
- **Session cookie:** signed with `IH_SESSION_SECRET`, `HttpOnly`, `SameSite=Lax`, `Secure` when `IH_PUBLIC_URL` starts with `https`, and valid for 8 hours. The CSRF token cookie `ih_csrf` (readable by the web app by design, `SameSite=Lax`, same `Secure` rule) has the same lifetime, and unsafe cookie-session requests must echo it in `X-CSRF-Token`. API-key and bearer-token requests do not use cookies and are not subject to CSRF.
