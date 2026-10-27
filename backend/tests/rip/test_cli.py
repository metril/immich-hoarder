import json
import signal
import uuid
from pathlib import Path

import httpx
import pytest
import respx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.crypto import SecretBox
from app.db.engine import make_sync_engine
from app.db.models import AssetSeen, Base, ImmichTarget, Setting, Source, User
from app.rip.cli import main

BASE = "http://immich.test/api"
KEY = "test-master-key-0123456789abcdef-xyz"


def _mock_immich(router: respx.MockRouter) -> list[str]:
    ups: list[str] = []
    album = str(uuid.uuid4())

    def bulk(req: httpx.Request) -> httpx.Response:
        items = json.loads(req.content)["assets"]
        return httpx.Response(
            200, json={"results": [{"id": a["id"], "action": "accept"} for a in items]}
        )

    def upload(req: httpx.Request) -> httpx.Response:
        aid = str(uuid.uuid4())
        ups.append(aid)
        return httpx.Response(201, json={"id": aid, "status": "created"})

    def add(req: httpx.Request) -> httpx.Response:
        ids = json.loads(req.content)["ids"]
        return httpx.Response(200, json=[{"id": i, "success": True} for i in ids])

    router.post(f"{BASE}/assets/bulk-upload-check").mock(side_effect=bulk)
    router.post(f"{BASE}/assets").mock(side_effect=upload)
    router.get(f"{BASE}/albums").mock(return_value=httpx.Response(200, json=[]))
    router.post(f"{BASE}/albums").mock(
        return_value=httpx.Response(200, json={"id": album, "albumName": "x", "assetCount": 0})
    )
    router.put(f"{BASE}/albums/{album}/assets").mock(side_effect=add)
    router.put(url__regex=rf"{BASE}/assets/.+").mock(return_value=httpx.Response(200, json={}))
    return ups


@pytest.fixture
def db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[str, int]:
    url = f"sqlite+aiosqlite:///{tmp_path / 'c.db'}"
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setenv("IH_DATABASE_URL", url)
    monkeypatch.setenv("IH_MASTER_KEY", KEY)
    monkeypatch.setenv("IH_SCRATCH_DIR", str(scratch))
    get_settings.cache_clear()
    eng = make_sync_engine(url)
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        u = User(sub="u1")
        s.add(u)
        s.flush()
        t = ImmichTarget(
            owner_id=u.id,
            name="t",
            url="http://immich.test",
            api_key_enc=SecretBox(KEY).encrypt(b"k"),
        )
        s.add(t)
        s.add(Setting(key="rip", value={"allow_private_hosts": True}))
        s.flush()
        s.add(
            Source(
                id=5,
                owner_id=u.id,
                name="s",
                url="http://placeholder/",
                extractor="directlink",
                target_id=t.id,
            )
        )
        s.commit()
    eng.dispose()
    yield url, 5
    get_settings.cache_clear()


def _count(url: str) -> int:
    eng = make_sync_engine(url)
    try:
        with Session(eng) as s:
            return int(s.execute(select(func.count()).select_from(AssetSeen)).scalar() or 0)
    finally:
        eng.dispose()


def test_cli_run_end_to_end(
    db: tuple[str, int], img_server: str, capsys: pytest.CaptureFixture[str]
) -> None:
    url, sid = db
    eng = make_sync_engine(url)
    with Session(eng) as s:
        src = s.get(Source, sid)
        assert src is not None
        src.url = f"{img_server}/img/a.jpg"
        s.commit()
    eng.dispose()
    before = (signal.getsignal(signal.SIGINT), signal.getsignal(signal.SIGTERM))
    with respx.mock(assert_all_called=False) as router:
        ups = _mock_immich(router)
        code = main(["run", "--source-id", str(sid)])
    assert code == 0
    assert before == (signal.getsignal(signal.SIGINT), signal.getsignal(signal.SIGTERM))
    out = capsys.readouterr().out
    events = [json.loads(line) for line in out.splitlines() if line]
    assert "item.uploaded" in [e["type"] for e in events]
    assert len(ups) == 1
    assert _count(url) == 1
    # second run is incremental and uploads nothing
    with respx.mock(assert_all_called=False) as router:
        ups2 = _mock_immich(router)
        assert main(["run", "--source-id", str(sid), "--log-level", "debug"]) == 0
    assert ups2 == []


def test_cli_unknown_source_exit_1(db: tuple[str, int]) -> None:
    assert main(["run", "--source-id", "999"]) == 1
