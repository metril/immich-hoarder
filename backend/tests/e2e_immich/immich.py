"""Minimal Immich admin client for the e2e stack."""

import httpx

_EMAIL = "admin@e2e.test"
_PASSWORD = "e2e-password-123"


class ImmichAdmin:
    def __init__(self, base_url: str) -> None:
        self.http = httpx.Client(base_url=base_url.rstrip("/"), timeout=60)

    def bootstrap(self) -> str:
        """Create the admin, log in, mint an all-permission API key; return its secret."""
        r = self.http.post(
            "/api/auth/admin-sign-up",
            json={"email": _EMAIL, "password": _PASSWORD, "name": "E2E Admin"},
        )
        r.raise_for_status()
        r = self.http.post("/api/auth/login", json={"email": _EMAIL, "password": _PASSWORD})
        r.raise_for_status()
        token = r.json()["accessToken"]
        r = self.http.post(
            "/api/api-keys",
            json={"name": "e2e", "permissions": ["all"]},
            headers={"Authorization": f"Bearer {token}"},
        )
        r.raise_for_status()
        secret = r.json()["secret"]
        self.http.headers["x-api-key"] = secret
        return secret

    def album_assets(self, name: str) -> list[dict]:
        r = self.http.get("/api/albums")
        r.raise_for_status()
        ids = [a["id"] for a in r.json() if a["albumName"] == name]
        if not ids:
            return []
        r = self.http.post("/api/search/metadata", json={"albumIds": ids, "size": 1000})
        r.raise_for_status()
        return r.json()["assets"]["items"]

    def asset(self, asset_id: str) -> dict:
        r = self.http.get(f"/api/assets/{asset_id}")
        r.raise_for_status()
        return r.json()

    def count_assets(self) -> int:
        r = self.http.post("/api/search/metadata", json={"size": 1000, "withDeleted": False})
        r.raise_for_status()
        return len(r.json()["assets"]["items"])

    def delete(self, ids: list[str], force: bool = True) -> None:
        r = self.http.request("DELETE", "/api/assets", json={"ids": ids, "force": force})
        r.raise_for_status()
