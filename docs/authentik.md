# Authentik OIDC

Examples use `auth.example.com` for Authentik and `hoarder.example.com` for the app.

## 1. Provider

Create an **OAuth2/OpenID Provider**:

- Client type: **Confidential**.
- Redirect URI (strict): `https://hoarder.example.com/api/v1/auth/callback`
- Signing key: an RS256 or ES256 key. The app accepts only these algorithms.
- Scopes: `openid`, `email`, `profile`. In Authentik the `profile` scope carries the `groups` claim, through the mapping "authentik default OAuth Mapping: OpenID 'profile'". Keep that mapping selected under Provider > Advanced protocol settings > Scopes. Without it no groups arrive and every user gets a 403. The app also requests a `groups` scope; Authentik has no such scope and ignores it.

Note the client id and client secret.

## 2. Application

Create an application with slug `hoarder` using that provider. The issuer is then:

```
https://auth.example.com/application/o/hoarder/
```

## 3. Groups

Create the groups `hoarder-admins` and `hoarder-users` and add people to them. Roles come only from groups and are refreshed on every login and bearer-token use.

## 4. App configuration

In the web UI open **Settings → Auth** (create the local admin on `/setup` first if this is a fresh install). Set the public URL, then enable OIDC and enter the issuer, client id, client secret, admin groups (`hoarder-admins`), user groups (`hoarder-users`) and groups claim (`groups`). Group fields accept several groups per role. The client secret is stored encrypted. No environment variables are needed.

## Users in neither group, and disabled users

Role resolution (`resolve_role` in `app/auth/principal.py`) gives the admin role if any of the user's groups is in the configured admin groups, otherwise the user role if any is in the configured user groups, otherwise no role. A user with no role:

- is denied at login with `403 access denied` and no session is created (the user record and groups are still stored);
- is rejected with `401` on any later session or bearer-token request, including API keys, even if they had access before. Removing someone from the groups takes effect on their next request.

Disabled users are treated the same way: 403 at login, 401 afterwards.

## API bearer tokens

Bearer tokens from the same provider are accepted for the API. The token must be signed RS256 or ES256, issued by the configured issuer, include `exp` and `sub`, and have `aud` equal to the client id.
