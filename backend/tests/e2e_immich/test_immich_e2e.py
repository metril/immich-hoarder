import time

import pytest

pytestmark = pytest.mark.immich_e2e

_TERMINAL = {"succeeded", "failed", "cancelled"}


def _wait(stack, job_id: int) -> dict:
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        r = stack.hoarder.get(f"/api/v1/jobs/{job_id}")
        r.raise_for_status()
        if r.json()["status"] in _TERMINAL:
            return r.json()
        time.sleep(1)
    raise TimeoutError(f"job {job_id} did not finish")


def _create(stack, name: str) -> int:
    r = stack.hoarder.post(
        "/api/v1/sources",
        json={
            "name": name,
            "url": stack.site_url(name),
            "target_id": stack.target_id,
            "album_template": "E2E",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _run_source(stack, source_id: int) -> dict:
    r = stack.hoarder.post(f"/api/v1/sources/{source_id}/run")
    assert r.status_code == 202, r.text
    return _wait(stack, r.json()["id"])


def test_full_cycle(stack):
    imm = stack.immich
    ids = {}

    def run(name: str) -> dict:
        ids[name] = _create(stack, name)
        return _run_source(stack, ids[name])

    # 1. upload with metadata
    for n in ("a.jpg", "b.jpg"):
        job = run(n)
        assert job["status"] == "succeeded", job
        assert job["counters"]["uploaded"] == 1, job
    items = imm.album_assets("E2E")
    assert len(items) == 2

    a_id = None
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        for it in imm.album_assets("E2E"):
            full = imm.asset(it["id"])
            exif = full.get("exifInfo") or {}
            if (exif.get("dateTimeOriginal") or "").startswith("2021-05-04T03:02:01"):
                a_id = it["id"]
                desc = exif
        if a_id:
            break
        time.sleep(2)
    assert a_id, "metadata extraction for a.jpg never produced DateTimeOriginal"
    assert stack.site_url("a.jpg") in desc["description"]
    b_id = next(i["id"] for i in imm.album_assets("E2E") if i["id"] != a_id)

    # 2. byte-identical copy is linked, not uploaded
    job = run("c.jpg")
    assert job["status"] == "succeeded", job
    assert job["counters"]["linked"] == 1, job
    assert job["counters"]["uploaded"] == 0, job
    assert len(imm.album_assets("E2E")) == 2
    assert imm.count_assets() == 2

    # 3. re-runs upload nothing
    uploaded = 0
    for n in ("a.jpg", "b.jpg", "c.jpg"):
        job = _run_source(stack, ids[n])
        assert job["status"] == "succeeded", job
        uploaded += job["counters"]["uploaded"]
    assert uploaded == 0
    assert imm.count_assets() == 2

    # 4. deleted in Immich: same bytes from a new source are not re-uploaded
    imm.delete([b_id], force=True)
    job = run("d.jpg")
    assert job["status"] == "succeeded", job
    assert job["counters"]["deleted_in_immich"] == 1, job
    assert job["counters"]["uploaded"] == 0, job
    assert imm.count_assets() == 1
