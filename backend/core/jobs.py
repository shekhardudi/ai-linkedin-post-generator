"""In-process async job runner with a JSONL store.

Suitable for a single-replica portfolio app — no Redis, no Celery. If we ever
need horizontal scale we'd swap JobStore for a database and JobRunner for a
real queue, without touching the API surface.
"""

from __future__ import annotations

import asyncio
import json
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from .logging import get_logger
from .paths import jobs_dir

log = get_logger("jobs")


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


@dataclass
class Job:
    id: str
    kind: str  # "scout" | "posts"
    status: JobStatus
    created_at: str
    updated_at: str
    inputs: dict[str, Any]
    progress: dict[str, Any] = field(default_factory=dict)
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# JobStore — append-only JSONL per kind, in-memory index by job_id.
# ---------------------------------------------------------------------------

class JobStore:
    def __init__(self, root: Optional[Path] = None) -> None:
        self._root = root or jobs_dir()
        self._lock = threading.Lock()
        self._jobs: dict[str, Job] = {}
        self._load_existing()

    def _file_for(self, kind: str) -> Path:
        return self._root / f"{kind}.jsonl"

    def _load_existing(self) -> None:
        for kind in ("scout", "posts"):
            f = self._file_for(kind)
            if not f.exists():
                continue
            for raw in f.read_text(encoding="utf-8").splitlines():
                if not raw.strip():
                    continue
                try:
                    data = json.loads(raw)
                    job = Job(
                        id=data["id"],
                        kind=data["kind"],
                        status=JobStatus(data["status"]),
                        created_at=data["created_at"],
                        updated_at=data["updated_at"],
                        inputs=data.get("inputs", {}),
                        progress=data.get("progress", {}),
                        result=data.get("result"),
                        error=data.get("error"),
                    )
                    self._jobs[job.id] = job
                except Exception as exc:  # corrupt line — skip
                    log.warning("job.load.skip", error=str(exc), line=raw[:200])

    def _persist(self, job: Job) -> None:
        line = json.dumps(job.to_dict()) + "\n"
        with self._lock:
            self._file_for(job.kind).open("a", encoding="utf-8").write(line)

    def create(self, kind: str, inputs: dict[str, Any]) -> Job:
        job = Job(
            id=uuid.uuid4().hex,
            kind=kind,
            status=JobStatus.queued,
            created_at=_now(),
            updated_at=_now(),
            inputs=inputs,
        )
        with self._lock:
            self._jobs[job.id] = job
        self._persist(job)
        log.info("job.created", job_id=job.id, kind=kind)
        return job

    def update(
        self,
        job_id: str,
        *,
        status: Optional[JobStatus] = None,
        progress: Optional[dict[str, Any]] = None,
        result: Optional[dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> Job:
        with self._lock:
            job = self._jobs[job_id]
            if status is not None:
                job.status = status
            if progress is not None:
                job.progress = progress
            if result is not None:
                job.result = result
            if error is not None:
                job.error = error
            job.updated_at = _now()
        self._persist(job)
        log.info(
            "job.updated",
            job_id=job_id,
            status=job.status.value,
            progress=job.progress,
            has_error=bool(error),
        )
        return job

    def get(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    def list(self, kind: Optional[str] = None, limit: int = 50) -> list[Job]:
        jobs = list(self._jobs.values())
        if kind:
            jobs = [j for j in jobs if j.kind == kind]
        jobs.sort(key=lambda j: j.created_at, reverse=True)
        return jobs[:limit]

    def cancel_inflight(self) -> int:
        """Mark queued/running jobs as cancelled. Used at shutdown."""
        n = 0
        for job in list(self._jobs.values()):
            if job.status in (JobStatus.queued, JobStatus.running):
                self.update(job.id, status=JobStatus.cancelled, error="server shutdown")
                n += 1
        return n


# ---------------------------------------------------------------------------
# JobRunner — schedules sync engine work on a thread pool, owned by store.
# ---------------------------------------------------------------------------

class JobRunner:
    def __init__(self, store: JobStore, *, max_concurrent: int = 2) -> None:
        self._store = store
        self._sem = asyncio.Semaphore(max_concurrent)
        self._tasks: dict[str, asyncio.Task] = {}

    def schedule(
        self,
        job: Job,
        worker: Callable[[Job, JobStore], Awaitable[dict[str, Any]]],
    ) -> None:
        """Schedule a coroutine worker against the running event loop."""
        task = asyncio.create_task(self._run(job, worker))
        self._tasks[job.id] = task

    async def _run(
        self,
        job: Job,
        worker: Callable[[Job, JobStore], Awaitable[dict[str, Any]]],
    ) -> None:
        async with self._sem:
            self._store.update(job.id, status=JobStatus.running)
            try:
                result = await worker(job, self._store)
                self._store.update(job.id, status=JobStatus.completed, result=result)
            except asyncio.CancelledError:
                self._store.update(job.id, status=JobStatus.cancelled, error="cancelled")
                raise
            except Exception as exc:
                log.exception("job.failed", job_id=job.id, kind=job.kind)
                self._store.update(job.id, status=JobStatus.failed, error=str(exc))
            finally:
                self._tasks.pop(job.id, None)

    async def shutdown(self) -> None:
        for t in list(self._tasks.values()):
            t.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks.values(), return_exceptions=True)
