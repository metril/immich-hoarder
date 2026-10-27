import re
from pathlib import Path
from typing import Any

import yaml

from app.rip.settings import DEFAULT_SCRATCH_MAX_BYTES

ROOT = Path(__file__).parents[2]
BASE = ROOT / "compose.example.yml"
PG = ROOT / "deploy" / "compose.postgres.yml"
VPN = ROOT / "deploy" / "compose.gluetun.yml"
SVC = "immich-hoarder"


def _load(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text())  # type: ignore[no-any-return]


def _env(service: dict[str, Any]) -> dict[str, str]:
    env = service.get("environment", {})
    if isinstance(env, list):
        return dict(e.split("=", 1) for e in env)
    return {k: str(v) for k, v in env.items()}


def test_compose_invariants() -> None:
    s = _load(BASE)["services"][SVC]
    assert s["read_only"] is True
    assert s["stop_grace_period"] == "30s"
    assert "/scratch:size=4g,uid=10001,gid=10001" in s["tmpfs"]
    assert DEFAULT_SCRATCH_MAX_BYTES == 4 * 1024**3
    assert "/tmp" in s["tmpfs"]
    assert "ports" not in s
    assert "healthcheck" not in s
    assert s["security_opt"] == ["no-new-privileges:true"]
    assert s["cap_drop"] == ["ALL"]
    assert s["restart"] == "unless-stopped"
    assert s["networks"] == ["default", "traefik"]
    assert _load(BASE)["networks"]["traefik"]["external"] is True


def test_traefik_labels() -> None:
    s = _load(BASE)["services"][SVC]
    labels = set(s["labels"])
    assert {
        "traefik.enable=true",
        "traefik.http.routers.hoarder.rule=Host(`hoarder.example.com`)",
        "traefik.http.routers.hoarder.entrypoints=websecure",
        "traefik.http.routers.hoarder.tls.certresolver=letsencrypt",
        "traefik.http.services.hoarder.loadbalancer.server.port=8080",
        "traefik.docker.network=traefik",
    } <= labels
    assert not any(k.startswith(("IH_OIDC_", "IH_PUBLIC_URL")) for k in _env(s))


def test_secrets_are_files() -> None:
    env = _env(_load(BASE)["services"][SVC])
    assert not {"IH_MASTER_KEY", "IH_SESSION_SECRET"} & env.keys()
    for key in env:
        if re.search(r"SECRET|KEY|PASSWORD|TOKEN", key) and not key.endswith("_FILE"):
            raise AssertionError(f"{key} looks like a literal secret")


def test_postgres_override() -> None:
    data = _load(PG)
    pg = data["services"]["postgres"]
    assert re.fullmatch(r"postgres:17\.11-alpine@sha256:[0-9a-f]{64}", pg["image"])
    assert _env(pg)["POSTGRES_PASSWORD_FILE"].startswith("/run/secrets/")
    assert "pg_isready" in " ".join(pg["healthcheck"]["test"])
    assert any(str(v).startswith("ih_pg:") for v in pg["volumes"])
    assert "ih_pg" in data["volumes"]
    app = data["services"][SVC]
    assert app["depends_on"]["postgres"]["condition"] == "service_healthy"
    assert _env(app)["IH_DATABASE_URL_FILE"] == "/run/secrets/ih_db_url"
    assert "ih_db_url" in data["secrets"]


def test_gluetun_override() -> None:
    data = _load(VPN)
    g = data["services"]["gluetun"]
    assert re.fullmatch(r"qmcgaw/gluetun:v3\.41\.2@sha256:[0-9a-f]{64}", g["image"])
    assert g["cap_add"] == ["NET_ADMIN"]
    assert g["devices"] == ["/dev/net/tun:/dev/net/tun"]
    env = _env(g)
    assert env["HTTPPROXY"] == "on"
    assert env["HTTPPROXY_LISTENING_ADDRESS"] == ":8888"
    assert "traefik" not in g.get("networks", [])
    text = VPN.read_text()
    assert "http://gluetun:8888" in text
    assert "allow_private_hosts" in text


def test_images_pinned_by_digest() -> None:
    for path in (BASE, PG, VPN):
        for name, svc in _load(path)["services"].items():
            image = svc.get("image")
            if image is None or name == SVC:
                continue  # our own image is not digest-pinned (floating tag)
            assert re.search(r"@sha256:[0-9a-f]{64}$", image), f"{path.name}:{name}"
