"""HTTP API and the single-page site."""
from __future__ import annotations

import base64
import hashlib
import logging
import re
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .catalog import TEMPLATES, THEMES
from .config import Settings
from .jobs import JobManager, Refused
from .pipeline import FILES, Builder
from .planner import ClaudePlanner, MAX_PROMPT, Planner

log = logging.getLogger(__name__)

STATIC = Path(__file__).parent / "static"
LOCAL_THREE = Path(__file__).parent.parent / "node_modules" / "three"
CDN_THREE = "https://cdn.jsdelivr.net/npm/three@0.170.0"

MEDIA_TYPES = {".glb": "model/gltf-binary", ".png": "image/png", ".json": "application/json",
               ".csv": "text/csv; charset=utf-8", ".mpd": "text/plain; charset=utf-8"}


class JobRequest(BaseModel):
    prompt: str = Field(min_length=2, max_length=MAX_PROMPT)


def create_app(settings: Settings | None = None, planner: Planner | None = None,
               builder: Builder | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    if planner is None:
        planner = Planner(ClaudePlanner(settings.model) if settings.use_claude else None)
    builder = builder or Builder(settings)
    manager = JobManager(settings, planner, builder)

    if settings.three_url:
        three = settings.three_url.rstrip("/")
    elif LOCAL_THREE.exists():
        three = "/vendor/three"
    else:
        three = CDN_THREE
    three_origin = "" if three.startswith("/") else "{0.scheme}://{0.netloc}".format(urlsplit(three))
    index_html = (STATIC / "index.html").read_text(encoding="utf-8").replace("%THREE%", three)
    # The import map is the page's only inline script; allow exactly that text.
    importmap = re.search(r'<script type="importmap">(.*?)</script>', index_html, re.S).group(1)
    importmap_hash = base64.b64encode(hashlib.sha256(importmap.encode()).digest()).decode()
    csp = ("default-src 'self'; "
           f"script-src 'self' 'sha256-{importmap_hash}' 'wasm-unsafe-eval' {three_origin}; "
           f"connect-src 'self' {three_origin}; "
           "img-src 'self' data: blob:; worker-src 'self' blob:; style-src 'self'; "
           "object-src 'none'; base-uri 'none'; frame-ancestors 'none'")

    @asynccontextmanager
    async def lifespan(app):
        yield
        manager.shutdown()

    app = FastAPI(title="BrickGen", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.manager = manager
    app.state.settings = settings

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        if response.headers.get("content-type", "").startswith("text/html"):
            response.headers["Content-Security-Policy"] = csp
        return response

    @app.get("/", response_class=HTMLResponse)
    def index():
        return index_html

    @app.get("/api/health")
    def health():
        status = builder.nova.status()
        return {"ok": all(status.values()), "planner": planner.mode, "model": settings.model if planner.claude else None,
                "tools": status}

    @app.get("/api/themes")
    def themes():
        kinds = {"vehicle": "Транспорт", "example": "Здания и корабль", "generator": "Новые генераторы"}
        groups: dict[str, list] = {}
        for t in TEMPLATES.values():
            groups.setdefault(kinds[t.kind], []).append(t.title)
        return {"themes": [dict(label=label, prompt=prompt) for label, prompt in THEMES],
                "catalog": [dict(group=g, titles=titles) for g, titles in groups.items()]}

    @app.post("/api/jobs", status_code=202)
    def submit(body: JobRequest, request: Request):
        prompt = " ".join(body.prompt.split())
        if len(prompt) < 2:
            raise HTTPException(422, "Опишите модель хотя бы парой слов.")
        client = request.client.host if request.client else "unknown"
        try:
            job = manager.submit(prompt, client)
        except Refused as refused:
            return JSONResponse({"detail": str(refused)}, status_code=refused.status)
        return {"id": job.id}

    @app.get("/api/jobs/{job_id}")
    def job(job_id: str):
        found = manager.get(job_id)
        if found is None:
            raise HTTPException(404, "Модель не найдена.")
        return found.public(manager.position(found))

    @app.get("/files/{job_id}/{name}")
    def file(job_id: str, name: str, download: bool = False):
        found = manager.get(job_id)
        if found is None or name not in FILES:
            raise HTTPException(404)
        path = manager.folder(found.id) / FILES[name]
        if not path.is_file():
            raise HTTPException(404)
        suffix = "".join(Path(name).suffixes[-1:])
        headers = {"Cache-Control": "public, max-age=86400, immutable"}
        filename = None
        if download:
            stem = (found.draft or {}).get("template", "model")
            filename = f"{stem}-{found.id[:6]}{''.join(Path(name).suffixes)}"
        return FileResponse(path, media_type=MEDIA_TYPES.get(suffix, "application/octet-stream"),
                            filename=filename, headers=headers)

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    if three == "/vendor/three":
        app.mount("/vendor/three", StaticFiles(directory=LOCAL_THREE), name="three")
    return app
