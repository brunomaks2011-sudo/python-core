"""Jobs: one folder per request, built in a small thread pool, state kept in job.json."""
from __future__ import annotations

import json
import logging
import re
import secrets
import subprocess
import threading
import time
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .catalog import COLOURS, TEMPLATES
from .config import Settings
from .pipeline import Builder, NovaError
from .planner import NotUnderstood, Planner

log = logging.getLogger(__name__)

JOB_ID = re.compile(r"^[A-Za-z0-9_-]{8,32}$")

STAGES = ("plan", "draft", "review", "glb")

SUGGESTION = "Попробуйте: спортивная машина, экскаватор, робот, самолёт, космический корабль или дом."


class Refused(Exception):
    """The request cannot be queued now; the message is shown to the visitor."""

    def __init__(self, message: str, status: int):
        super().__init__(message)
        self.status = status


@dataclass
class Job:
    id: str
    prompt: str
    created: float
    state: str = "queued"  # queued, running, done, failed
    stages: dict = field(default_factory=lambda: {s: {"status": "pending"} for s in STAGES})
    draft: dict | None = None
    result: dict | None = None
    error: str | None = None
    finished: float | None = None

    def public(self, position: int | None = None) -> dict:
        data = asdict(self)
        data["position"] = position
        if self.draft:
            template = TEMPLATES.get(self.draft["template"])
            data["template"] = template and dict(key=template.key, title=template.title, kind=template.kind,
                                                 attribution=template.attribution)
            data["colours"] = [dict(role=template.role(k).label if template and template.role(k) else k,
                                    colour=COLOURS[c].label, hex=COLOURS[c].hex)
                               for k, c in self.draft.get("colours", {}).items() if c in COLOURS]
        return data


class RateLimiter:
    def __init__(self, per_hour: int):
        self.per_hour = per_hour
        self.hits: dict[str, deque] = defaultdict(deque)
        self.lock = threading.Lock()

    def allow(self, client: str) -> bool:
        now = time.monotonic()
        with self.lock:
            hits = self.hits[client]
            while hits and now - hits[0] > 3600:
                hits.popleft()
            if len(hits) >= self.per_hour:
                return False
            hits.append(now)
            return True


class JobManager:
    def __init__(self, settings: Settings, planner: Planner, builder: Builder):
        self.settings = settings
        self.planner = planner
        self.builder = builder
        self.root = settings.data_dir / "jobs"
        self.root.mkdir(parents=True, exist_ok=True)
        self.jobs: dict[str, Job] = {}
        self.lock = threading.Lock()
        self.limiter = RateLimiter(settings.jobs_per_hour)
        self.pool = ThreadPoolExecutor(max_workers=settings.workers, thread_name_prefix="job")
        self._recover()

    def _recover(self) -> None:
        """Jobs interrupted by a restart cannot resume: mark them failed."""
        for path in self.root.glob("*/job.json"):
            try:
                job = Job(**json.loads(path.read_text(encoding="utf-8")))
            except (ValueError, TypeError):
                continue
            if job.state in ("queued", "running"):
                job.state, job.error, job.finished = "failed", "Сервер перезапускался. Запустите сборку ещё раз.", time.time()
                self._save(job)

    def folder(self, job_id: str) -> Path:
        return self.root / job_id

    def _save(self, job: Job) -> None:
        folder = self.folder(job.id)
        folder.mkdir(parents=True, exist_ok=True)
        tmp = folder / "job.json.tmp"
        tmp.write_text(json.dumps(asdict(job), ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(folder / "job.json")

    def get(self, job_id: str) -> Job | None:
        if not JOB_ID.match(job_id):
            return None
        with self.lock:
            if job_id in self.jobs:
                return self.jobs[job_id]
        path = self.folder(job_id) / "job.json"
        if not path.exists():
            return None
        try:
            return Job(**json.loads(path.read_text(encoding="utf-8")))
        except (ValueError, TypeError):
            return None

    def position(self, job: Job) -> int | None:
        if job.state != "queued":
            return None
        with self.lock:
            queued = sorted((j for j in self.jobs.values() if j.state == "queued"), key=lambda j: j.created)
        return next((i + 1 for i, j in enumerate(queued) if j.id == job.id), None)

    def submit(self, prompt: str, client: str) -> Job:
        with self.lock:
            waiting = sum(1 for j in self.jobs.values() if j.state in ("queued", "running"))
        if waiting >= self.settings.max_queue + self.settings.workers:
            raise Refused("Сейчас собирается слишком много моделей. Попробуйте через пару минут.", 503)
        if not self.limiter.allow(client):
            raise Refused("Лимит сборок на этот час исчерпан. Попробуйте позже.", 429)
        job = Job(id=secrets.token_urlsafe(12), prompt=prompt, created=time.time())
        with self.lock:
            self.jobs[job.id] = job
        self._save(job)
        self.pool.submit(self._run, job)
        return job

    def _stage(self, job: Job, stage: str, status: str, **extra) -> None:
        entry = job.stages[stage]
        entry["status"] = status
        entry["started" if status == "running" else "finished"] = time.time()
        entry.update(extra)
        self._save(job)

    def _run(self, job: Job) -> None:
        job.state = "running"
        folder = self.folder(job.id)
        stage = "plan"
        try:
            self._stage(job, "plan", "running")
            draft = self.planner.plan(job.prompt)
            job.draft = draft.model_dump()
            self._stage(job, "plan", "done")

            stage = "draft"
            self._stage(job, "draft", "running")
            self.builder.make_plan(draft, folder)
            self._stage(job, "draft", "done")

            stage = "review"
            self._stage(job, "review", "running")
            review = self.builder.review(folder)
            self._stage(job, "review", "done" if review.get("checks_passed") else "failed")

            stage = "glb"
            self._stage(job, "glb", "running")
            glb_error = self.builder.glb(folder)
            self._stage(job, "glb", "failed" if glb_error else "done")

            job.result = self.builder.collect(folder, review, glb_error)
            job.state = "done"
        except NotUnderstood:
            job.state, job.error = "failed", "Не получилось понять, какую модель собрать. " + SUGGESTION
        except subprocess.TimeoutExpired:
            job.state, job.error = "failed", "Сборка заняла слишком много времени и была остановлена."
        except NovaError as error:
            job.state, job.error = "failed", str(error)
        except Exception:
            log.exception("job %s failed", job.id)
            job.state, job.error = "failed", "Внутренняя ошибка при сборке. Попробуйте ещё раз."
        if job.state == "failed" and job.stages[stage]["status"] == "running":
            job.stages[stage]["status"] = "failed"
        job.finished = time.time()
        self._save(job)
        with self.lock:
            self.jobs.pop(job.id, None)

    def shutdown(self) -> None:
        self.pool.shutdown(wait=False, cancel_futures=True)
