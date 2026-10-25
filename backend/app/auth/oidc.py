import asyncio
import time
from typing import Any

import httpx
import jwt
from authlib.integrations.starlette_client import OAuth

from app.core.config import Settings

JWKS_TTL = 600.0
FORCED_REFETCH_INTERVAL = 30.0


class TokenError(Exception):
    pass


def build_oauth(settings: Settings) -> OAuth | None:
    if not (settings.oidc_issuer and settings.oidc_client_id and settings.oidc_client_secret):
        return None
    oauth = OAuth()
    oauth.register(
        name="oidc",
        client_id=settings.oidc_client_id,
        client_secret=settings.oidc_client_secret.get_secret_value(),
        server_metadata_url=f"{settings.oidc_issuer.rstrip('/')}/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile groups", "code_challenge_method": "S256"},
    )
    return oauth


class BearerVerifier:
    def __init__(self, settings: Settings) -> None:
        self._s = settings
        self._keys: dict[str, Any] = {}
        self._fetched = 0.0
        self._forced_at: float | None = None
        self._lock = asyncio.Lock()

    async def _refresh(self) -> None:
        assert self._s.oidc_issuer
        async with httpx.AsyncClient(timeout=10) as http:
            disc = await http.get(
                f"{self._s.oidc_issuer.rstrip('/')}/.well-known/openid-configuration"
            )
            disc.raise_for_status()
            resp = await http.get(disc.json()["jwks_uri"])
            resp.raise_for_status()
        keys: dict[str, Any] = {}
        for jwk in resp.json().get("keys", []):
            if "kid" not in jwk or jwk.get("use", "sig") != "sig":
                continue
            try:
                keys[jwk["kid"]] = jwt.PyJWK(jwk).key
            except jwt.PyJWTError:
                continue
        self._keys, self._fetched = keys, time.monotonic()

    async def _key(self, kid: str) -> Any:
        async with self._lock:
            now = time.monotonic()
            if not self._keys or now - self._fetched > JWKS_TTL:
                await self._refresh()
            elif kid not in self._keys and (
                self._forced_at is None or now - self._forced_at >= FORCED_REFETCH_INTERVAL
            ):
                self._forced_at = now  # rate-limit unknown-kid refetches
                await self._refresh()
            if kid not in self._keys:
                raise TokenError("unknown kid")
            return self._keys[kid]

    async def verify(self, token: str) -> dict[str, Any]:
        s = self._s
        if not (s.oidc_issuer and s.oidc_client_id):
            raise TokenError("oidc not configured")
        try:
            kid = jwt.get_unverified_header(token).get("kid")
            if not kid:
                raise TokenError("missing kid")
            key = await self._key(kid)
            claims: dict[str, Any] = jwt.decode(
                token,
                key,
                algorithms=["RS256", "ES256"],
                issuer=s.oidc_issuer,
                audience=s.oidc_client_id,
                options={"require": ["exp", "sub"]},
            )
        except (jwt.PyJWTError, httpx.HTTPError, KeyError, ValueError) as e:
            raise TokenError(type(e).__name__) from e
        return claims
