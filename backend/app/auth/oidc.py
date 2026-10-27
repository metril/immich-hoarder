import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

import httpx
import jwt
from authlib.integrations.starlette_client import OAuth

JWKS_TTL = 600.0
FORCED_REFETCH_INTERVAL = 30.0


class TokenError(Exception):
    pass


@dataclass(frozen=True)
class OidcConfig:
    """Runtime OIDC configuration (client secret decrypted)."""

    enabled: bool = False
    issuer: str | None = None
    client_id: str | None = None
    client_secret: str | None = field(default=None, repr=False)
    admin_groups: tuple[str, ...] = ("hoarder-admins",)
    user_groups: tuple[str, ...] = ("hoarder-users",)
    groups_claim: str = "groups"

    @property
    def active(self) -> bool:
        return bool(self.enabled and self.issuer and self.client_id and self.client_secret)


def _discovery_url(issuer: str) -> str:
    return f"{issuer.rstrip('/')}/.well-known/openid-configuration"


async def discover(issuer: str) -> None:
    """Fetch the issuer's discovery document; raises ValueError with a short reason."""
    try:
        async with httpx.AsyncClient(timeout=10) as http:
            resp = await http.get(_discovery_url(issuer))
            resp.raise_for_status()
            doc = resp.json()
    except httpx.HTTPStatusError as e:
        raise ValueError(f"discovery returned HTTP {e.response.status_code}") from None
    except (httpx.HTTPError, ValueError):
        raise ValueError("discovery document could not be fetched") from None
    if not isinstance(doc, dict) or not all(
        doc.get(k) for k in ("authorization_endpoint", "token_endpoint", "jwks_uri")
    ):
        raise ValueError("discovery document is missing required endpoints")


def build_oauth(cfg: OidcConfig) -> OAuth | None:
    if not cfg.active:
        return None
    assert cfg.issuer and cfg.client_id and cfg.client_secret
    oauth = OAuth()
    oauth.register(
        name="oidc",
        client_id=cfg.client_id,
        client_secret=cfg.client_secret,
        server_metadata_url=_discovery_url(cfg.issuer),
        client_kwargs={"scope": "openid email profile groups", "code_challenge_method": "S256"},
    )
    return oauth


class BearerVerifier:
    def __init__(self, cfg: OidcConfig) -> None:
        self._s = cfg
        self._keys: dict[str, Any] = {}
        self._fetched = 0.0
        self._forced_at: float | None = None
        self._lock = asyncio.Lock()

    async def _refresh(self) -> None:
        assert self._s.issuer
        async with httpx.AsyncClient(timeout=10) as http:
            disc = await http.get(_discovery_url(self._s.issuer))
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
        if not (s.active and s.issuer and s.client_id):
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
                issuer=s.issuer,
                audience=s.client_id,
                options={"require": ["exp", "sub"]},
            )
        except (jwt.PyJWTError, httpx.HTTPError, KeyError, ValueError) as e:
            raise TokenError(type(e).__name__) from e
        return claims
