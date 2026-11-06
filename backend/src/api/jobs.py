"""Background optimization jobs: one worker thread, one active job, memory only.

A joint claim-age search takes minutes, longer than a browser request should
hang open. ``POST /optimize/jobs`` captures the inputs, hands the work to
:class:`JobRegistry`, and returns at once; the page polls the job.

Deliberately small (single-process deployment is an explicit assumption):

- One active job. A second submit while one is queued or running is refused
  (HTTP 409), so two multi-minute searches never share the CPU.
- Jobs live in memory. After a restart an id is unknown (404) and the page
  says the run was interrupted; the inputs are re-captured on the next run.
- :meth:`JobRegistry.shutdown` asks the running job to stop at its next
  progress report and waits for the thread. It returns whether the worker
  stopped: a job between progress reports, or saving its results, can
  outlast the wait, and the caller must then leave the database open.
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Literal

logger = logging.getLogger(__name__)

# The last phase: the results exist and are being saved. Not interruptible.
PREPARE_PHASE = "prepare"

Status = Literal["queued", "running", "done", "failed"]
# The work a job runs: given a progress callback, returns the stored run id.
Work = Callable[[Callable[[str, int, int], None]], str]


class JobBusyError(RuntimeError):
    """Another job is already queued or running."""

    def __init__(self, active_id: str) -> None:
        super().__init__(f"job {active_id} is still running")
        self.active_id = active_id


class JobInterrupted(Exception):
    """Raised inside a job's progress callback when the server is stopping."""


@dataclass
class Job:
    id: str
    household_id: str
    status: Status = "queued"
    phase: str | None = None
    progress: dict = field(default_factory=lambda: {"done": 0, "total": 0})
    run_id: str | None = None
    error: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    started_at: str | None = None
    finished_at: str | None = None


class JobRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, Job] = {}
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def submit(self, household_id: str, work: Work) -> dict:
        """Start *work* on the worker thread; :class:`JobBusyError` if busy."""
        with self._lock:
            active = self._active_locked()
            if active is not None:
                raise JobBusyError(active.id)
            job = Job(id=str(uuid.uuid4()), household_id=household_id)
            self._jobs[job.id] = job
            self._thread = threading.Thread(
                target=self._run, args=(job, work), name=f"optimize-job-{job.id[:8]}",
                daemon=True,
            )
            self._thread.start()
            return asdict(job)

    def get(self, job_id: str) -> dict | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return None if job is None else asdict(job)

    def active(self) -> dict | None:
        with self._lock:
            job = self._active_locked()
            return None if job is None else asdict(job)

    def shutdown(self, timeout: float | None = 60.0) -> bool:
        """Stop the running job at its next progress report and wait for it.

        Returns True once no worker is running; False if it outlasted *timeout*.
        """
        self._stop.set()
        thread = self._thread
        if thread is None:
            return True
        thread.join(timeout)
        if not thread.is_alive():
            return True
        job = self.active()
        logger.warning(
            "optimize job %s still running after %ss of shutdown (phase %s)",
            job and job["id"], timeout, job and job["phase"],
        )
        return False

    # -- worker ---------------------------------------------------------------

    def _active_locked(self) -> Job | None:
        return next((j for j in self._jobs.values() if j.status in ("queued", "running")),
                    None)

    def _run(self, job: Job, work: Work) -> None:
        def progress(phase: str, done: int, total: int) -> None:
            # Once the results exist ("prepare": saving them), finishing is
            # quicker and better than discarding them; shutdown waits for it.
            if self._stop.is_set() and phase != PREPARE_PHASE:
                raise JobInterrupted("server stopping")
            with self._lock:
                job.phase = phase
                job.progress = {"done": done, "total": total}

        with self._lock:
            job.status = "running"
            job.started_at = datetime.now().isoformat()
        t0 = time.monotonic()
        try:
            run_id = work(progress)
        except JobInterrupted:
            logger.info("optimize job %s interrupted in phase %s after %.1fs",
                        job.id, job.phase, time.monotonic() - t0)
            outcome: dict = {"status": "failed", "error": "interrupted: the server stopped"}
        except Exception as exc:  # the job's failure is its result, not the thread's
            logger.exception("optimize job %s (household %s) failed in phase %s after %.1fs",
                             job.id, job.household_id, job.phase, time.monotonic() - t0)
            outcome = {"status": "failed", "error": str(exc) or type(exc).__name__}
        else:
            outcome = {"status": "done", "run_id": run_id}
        with self._lock:
            for k, v in outcome.items():
                setattr(job, k, v)
            job.finished_at = datetime.now().isoformat()
