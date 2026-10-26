# Authentik OIDC

Examples use `auth.example.com` for Authentik and `hoarder.example.com` for the app.

## 1. Provider

Create an **OAuth2/OpenID Provider**:

- Client type: **Confidential**.
- Redirect URI (strict): `https://hoarder.example.com/api/v1/auth/callback`
- Signing key: an RS256 or ES256 key. The app accepts only these algorithms.
- Scopes: `openid`, `email`, `profile`. In Authentik the `profile` scope carries the `groups` claim. The app also requests a `groups` scope, which Authentik ignores if it has no mapping for it.

Note the client id and client secret.

## 2. Application

Create an application with slug `hoarder` using that provider. The issuer is then:

```
https://auth.example.com/application/o/hoarder/
```

## 3. Groups

Create the groups `hoarder-admins` and `hoarder-users` and add people to them. Roles come only from groups and are refreshed on every login and bearer-token use.

## 4. App configuration

```yaml
IH_OIDC_ISSUER: https://auth.example.com/application/o/hoarder/
IH_OIDC_CLIENT_ID: <client id>
IH_OIDC_CLIENT_SECRET_FILE: /run/secrets/ih_oidc_client_secret
IH_OIDC_ADMIN_GROUPS: '["hoarder-admins"]'
IH_OIDC_USER_GROUPS: '["hoarder-users"]'
IH_OIDC_GROUPS_CLAIM: groups
```

Both group variables are JSON lists, so several groups can map to one role. `IH_OIDC_GROUPS_CLAIM` names the claim that holds the groups (default `groups`).

## Users in neither group

Role resolution (`resolve_role` in `app/auth/principal.py`) gives the admin role if any of the user's groups is in `IH_OIDC_ADMIN_GROUPS`, otherwise the user role if any is in `IH_OIDC_USER_GROUPS`, otherwise no role. A user with no role:

- is denied at login with `403 access denied` and no session is created (the user record and groups are still stored);
- is rejected with `401` on any later session or bearer-token request, including API keys, even if they had access before. Removing someone from the groups takes effect on their next request.

## API bearer tokens

Bearer tokens from the same provider are accepted for the API. The token must be signed RS256 or ES256, issued by the configured issuer, include `exp` and `sub`, and have `aud` equal to the client id.
