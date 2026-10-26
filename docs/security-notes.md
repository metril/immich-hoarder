# Security notes

API-key requests use the role and groups from the user's last login or bearer-token use. Roles come only from OIDC groups and are refreshed on each login or bearer use. Disabling a user takes effect immediately, including for their API keys.

`MASTER_KEY` must be high-entropy (32+ random characters, e.g. `openssl rand -base64 48`). Encryption keys are derived with HKDF, which is not a password KDF and gives no protection to a guessable passphrase.

A missing target or credential returns 403, not 404, so the API does not reveal whether an id exists to callers who cannot access it.

User notification URLs (apprise credentials) are blocked from connecting to private addresses at resolve time, so a private `HTTP(S)_PROXY` environment variable also blocks those gated sends. Admin-configured global notification URLs are unaffected.

## Residual risks (accepted)

- DNS and proxy-target SSRF: the connect guard vets the addresses the host resolves to, but what an admin-configured proxy then connects to is the proxy's responsibility. Restrict the proxy's own egress.
- PostgreSQL 14 or later is required.
- `allow_private_hosts` (admin rip setting) disables the private-address guard for downloads. Enable it only on trusted networks; it applies to every source.
- The scratch soft cap can be overshot by the files already in flight when it is reached, and two concurrent near-duplicates of the same image can both be uploaded because neither is recorded yet when the other is checked.
