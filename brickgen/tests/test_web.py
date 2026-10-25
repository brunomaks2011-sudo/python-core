import base64
import dataclasses
import hashlib
import re
import time

import pytest
from fastapi.testclient import TestClient

from brickgen.web import create_app
from conftest import FakeBuilder


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings, builder=FakeBuilder(settings))) as client:
        yield client


def wait(client, job_id, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["state"] in ("done", "failed"):
            return job
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} did not finish")


def test_page_allows_only_its_own_import_map(client):
    response = client.get("/")
    assert response.status_code == 200
    importmap = re.search(r'<script type="importmap">(.*?)</script>', response.text, re.S).group(1)
    digest = base64.b64encode(hashlib.sha256(importmap.encode()).digest()).decode()
    csp = response.headers["content-security-policy"]
    assert f"'sha256-{digest}'" in csp and "default-src 'self'" in csp and "'unsafe-inline'" not in csp
    assert response.headers["x-content-type-options"] == "nosniff"


def test_themes_and_health(client):
    themes = client.get("/api/themes").json()
    assert len(themes["themes"]) == 6 and themes["catalog"]
    health = client.get("/api/health").json()
    assert health["planner"] == "rules" and health["model"] is None and set(health["tools"]) >= {"ldraw_nova", "leocad"}


def test_job_runs_through_all_stages(client):
    response = client.post("/api/jobs", json={"prompt": "  красный   робот "})
    assert response.status_code == 202
    job = wait(client, response.json()["id"])

    assert job["state"] == "done", job["error"]
    assert job["prompt"] == "красный робот"
    assert [stage["status"] for stage in job["stages"].values()] == ["done"] * 4
    assert job["template"]["key"] == "robot" and job["template"]["attribution"] is None
    assert job["colours"] == [{"role": "корпус", "colour": "красный", "hex": "#B40000"}]
    assert job["result"]["checks"]["passed"] and job["result"]["bom"][0]["quantity"] == 2
    assert set(job["result"]["files"]) >= {"model.glb", "model.mpd", "parts.csv", "preview.png"}


def test_files_are_served_from_an_allowlist(client):
    job = wait(client, client.post("/api/jobs", json={"prompt": "робот"}).json()["id"])
    glb = client.get(f"/files/{job['id']}/model.glb?download=1")
    assert glb.status_code == 200 and glb.content == b"glTF"
    assert glb.headers["content-type"] == "model/gltf-binary"
    assert f'filename="robot-{job["id"][:6]}.glb"' in glb.headers["content-disposition"]
    assert client.get(f"/files/{job['id']}/model.mpd").headers["content-type"].startswith("text/plain")
    for name in ("job.json", "..%2Fjob.json", "review%2Freview.json", "top.png"):
        assert client.get(f"/files/{job['id']}/{name}").status_code == 404
    assert client.get("/files/not-a-job/model.glb").status_code == 404
    assert client.get("/api/jobs/../../etc").status_code == 404


def test_unclear_request_fails_with_a_hint(client):
    job = wait(client, client.post("/api/jobs", json={"prompt": "напиши стихи"}).json()["id"])
    assert job["state"] == "failed" and "Попробуйте" in job["error"]
    assert job["stages"]["plan"]["status"] == "failed"


@pytest.mark.parametrize("prompt", ["a", "  ", "x" * 301])
def test_prompt_length_is_checked(client, prompt):
    assert client.post("/api/jobs", json={"prompt": prompt}).status_code == 422


def test_rate_limit_per_client(settings):
    settings = dataclasses.replace(settings, jobs_per_hour=1)
    with TestClient(create_app(settings, builder=FakeBuilder(settings))) as client:
        assert client.post("/api/jobs", json={"prompt": "робот"}).status_code == 202
        refused = client.post("/api/jobs", json={"prompt": "робот"})
        assert refused.status_code == 429 and "Лимит" in refused.json()["detail"]


def test_unfinished_jobs_are_marked_failed_after_a_restart(settings):
    with TestClient(create_app(settings, builder=FakeBuilder(settings))) as client:
        job_id = wait(client, client.post("/api/jobs", json={"prompt": "робот"}).json()["id"])["id"]
    path = settings.data_dir / "jobs" / job_id / "job.json"
    path.write_text(path.read_text(encoding="utf-8").replace('"state": "done"', '"state": "running"'), encoding="utf-8")
    with TestClient(create_app(settings, builder=FakeBuilder(settings))) as client:
        job = client.get(f"/api/jobs/{job_id}").json()
    assert job["state"] == "failed" and "перезапуск" in job["error"]
