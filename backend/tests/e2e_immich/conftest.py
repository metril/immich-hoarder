"""Fixtures for the real-Immich end-to-end test (IH_E2E_IMMICH=1, needs Docker)."""

import os
import shutil
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest
from PIL import Image

from e2e_immich.immich import ImmichAdmin

HERE = Path(__file__).parent
COMPOSE = HERE / "compose.yml"


def pytest_collection_modifyitems(config, items):
    if os.environ.get("IH_E2E_IMMICH") == "1":
        return
    skip = pytest.mark.skip(reason="set IH_E2E_IMMICH=1 to run (needs Docker)")
    for item in items:
        if "e2e_immich" in str(item.fspath):
            item.add_marker(skip)


@dataclass
class Stack:
    hoarder: httpx.Client
    immich: ImmichAdmin
    target_id: int = 0

    def site_url(self, name: str) -> str:
        return f"http://site/{name}"


def _noise(seed: int) -> Image.Image:
    import random

    rnd = random.Random(seed)
    img = Image.new("RGB", (640, 480))
    img.putdata(
        [(rnd.randrange(256), rnd.randrange(256), rnd.randrange(256)) for _ in range(640 * 480)]
    )
    return img


def _write_jpeg(path: Path, seed: int, when: str) -> None:
    exif = Image.Exif()
    exif[0x8769] = {0x9003: when}  # Exif IFD: DateTimeOriginal
    _noise(seed).save(path, "JPEG", quality=90, exif=exif)


def _fixtures(root: Path) -> Path:
    site = root / "site"
    site.mkdir()
    _write_jpeg(site / "a.jpg", 1, "2021:05:04 03:02:01")
    _write_jpeg(site / "b.jpg", 2, "2022:06:07 08:09:10")
    shutil.copyfile(site / "a.jpg", site / "c.jpg")
    shutil.copyfile(site / "b.jpg", site / "d.jpg")
    site.chmod(0o755)  # pytest tmp dirs are 0700; the nginx worker must read these
    for f in site.iterdir():
        f.chmod(0o644)
    return site


def _dc(project: str, site: Path, *args: str, **kw) -> subprocess.CompletedProcess:
    env = {**os.environ, "IH_E2E_SITE_DIR": str(site)}
    return subprocess.run(
        ["docker", "compose", "-p", project, "-f", str(COMPOSE), *args],
        env=env,
        text=True,
        capture_output=True,
        **kw,
    )


def _port(project: str, site: Path, service: str, port: int) -> int:
    out = _dc(project, site, "port", service, str(port), check=True).stdout.strip()
    return int(out.rsplit(":", 1)[1])


@pytest.fixture(scope="session")
def stack(tmp_path_factory):
    site = _fixtures(tmp_path_factory.mktemp("e2e"))
    project = f"ih-e2e-{uuid.uuid4().hex[:8]}"
    try:
        up = _dc(project, site, "up", "-d", "--wait", "--wait-timeout", "300")
        if up.returncode:
            raise RuntimeError(f"compose up failed:\n{up.stdout}\n{up.stderr}")
        immich_url = f"http://127.0.0.1:{_port(project, site, 'immich-server', 2283)}"
        oidc_port = _port(project, site, "oidc", 8080)
        hoarder_url = f"http://127.0.0.1:{_port(project, site, 'hoarder', 8080)}"

        tok = httpx.post(
            f"http://127.0.0.1:{oidc_port}/default/token",
            data={
                "grant_type": "client_credentials",
                "client_id": "immich-hoarder",
                "client_secret": "x",
                "scope": "openid",
            },
            headers={"Host": "oidc:8080"},  # so `iss` is the in-network issuer hoarder expects
            timeout=30,
        )
        tok.raise_for_status()
        immich = ImmichAdmin(immich_url)
        api_key = immich.bootstrap()

        hoarder = httpx.Client(
            base_url=hoarder_url,
            headers={"Authorization": f"Bearer {tok.json()['access_token']}"},
            timeout=60,
        )
        deadline = time.monotonic() + 60
        while True:
            try:
                if hoarder.get("/healthz").status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            if time.monotonic() > deadline:
                raise RuntimeError("hoarder did not become healthy")
            time.sleep(1)
        cur = hoarder.get("/api/v1/settings")
        cur.raise_for_status()
        rip = {**cur.json().get("rip", {}), "allow_private_hosts": True}
        hoarder.put("/api/v1/settings", json={"rip": rip}).raise_for_status()
        r = hoarder.post(
            "/api/v1/targets",
            json={"name": "e2e", "url": "http://immich-server:2283", "api_key": api_key},
        )
        r.raise_for_status()
        s = Stack(hoarder=hoarder, immich=immich, target_id=r.json()["id"])
        yield s
    finally:
        log_dir = os.environ.get("IH_E2E_LOG_DIR")
        if log_dir:
            Path(log_dir).mkdir(parents=True, exist_ok=True)
            logs = _dc(project, site, "logs", "--no-color")
            (Path(log_dir) / "compose.log").write_text(logs.stdout + logs.stderr)
        _dc(project, site, "down", "-v", "--remove-orphans")
