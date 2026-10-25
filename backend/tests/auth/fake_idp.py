import json
import time
from typing import Any

import httpx
import jwt
import respx
from cryptography.hazmat.primitives.asymmetric import rsa

ISSUER = "https://idp.test"
CLIENT_ID = "hoarder"
KID = "k1"


class FakeIdp:
    def __init__(self) -> None:
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.nonce: str | None = None
        self.next_claims: dict[str, Any] = {}
        self.extra_keys: list[dict[str, Any]] = []

    def jwks(self) -> dict[str, Any]:
        jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.key.public_key()))
        return {"keys": [*self.extra_keys, {**jwk, "kid": KID, "alg": "RS256", "use": "sig"}]}

    def make_token(
        self,
        sub: str,
        groups: list[str],
        exp: int | None = None,
        aud: str = CLIENT_ID,
        **extra: Any,
    ) -> str:
        now = int(time.time())
        claims = {
            "iss": ISSUER,
            "aud": aud,
            "sub": sub,
            "iat": now,
            "exp": exp if exp is not None else now + 300,
            "groups": groups,
            "email": f"{sub}@example.test",
            "name": sub,
            **extra,
        }
        return jwt.encode(claims, self.key, algorithm="RS256", headers={"kid": KID})

    def mount(self, router: respx.MockRouter) -> None:
        router.get(f"{ISSUER}/.well-known/openid-configuration").respond(
            json={
                "issuer": ISSUER,
                "authorization_endpoint": f"{ISSUER}/authorize",
                "token_endpoint": f"{ISSUER}/token",
                "jwks_uri": f"{ISSUER}/jwks",
                "id_token_signing_alg_values_supported": ["RS256"],
                "code_challenge_methods_supported": ["S256"],
            }
        )
        router.get(f"{ISSUER}/jwks").mock(
            side_effect=lambda _r: httpx.Response(200, json=self.jwks())
        )

        def token(_request: httpx.Request) -> httpx.Response:
            id_token = self.make_token(nonce=self.nonce, **self.next_claims)
            return httpx.Response(
                200,
                json={"access_token": "at", "token_type": "Bearer", "id_token": id_token},
            )

        router.post(f"{ISSUER}/token").mock(side_effect=token)
