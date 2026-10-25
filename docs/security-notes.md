# Security notes

API-key requests use the role and groups from the user's last login or bearer-token use. Roles come only from OIDC groups and are refreshed on each login or bearer use. Disabling a user takes effect immediately, including for their API keys.

`MASTER_KEY` must be high-entropy (32+ random characters, e.g. `openssl rand -base64 48`). Encryption keys are derived with HKDF, which is not a password KDF and gives no protection to a guessable passphrase.

A missing target or credential returns 403, not 404, so the API does not reveal whether an id exists to callers who cannot access it.
