"""JobRegistry: one worker, one active job, failures and shutdown as results."""
from __future__ import annotations

import threading
import time

import pytest
from src.api.jobs import JobBusyError, JobRegistry


def _wait(reg: JobRegistry, job_id: str, timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = reg.get(job_id)
        if job["status"] in ("done", "failed"):
            return job
        time.sleep(0.01)
    raise AssertionError(f"job did not finish: {reg.get(job_id)}")


def test_a_job_reports_progress_and_its_run_id():
    reg = JobRegistry()
    seen = threading.Event()
    release = threading.Event()

    def work(progress):
        progress("deterministic", 3, 48)
        seen.set()
        release.wait(5)
        return "run-1"

    job = reg.submit("hh", work)
    assert job["status"] in ("queued", "running") and job["household_id"] == "hh"
    assert seen.wait(5)
    mid = reg.get(job["id"])
    assert mid["status"] == "running" and mid["phase"] == "deterministic"
    assert mid["progress"] == {"done": 3, "total": 48}
    assert reg.active()["id"] == job["id"]
    release.set()
    done = _wait(reg, job["id"])
    assert done["status"] == "done" and done["run_id"] == "run-1" and done["error"] is None
    assert done["started_at"] and done["finished_at"]
    assert reg.active() is None


def test_a_second_job_is_refused_while_one_runs():
    reg = JobRegistry()
    release = threading.Event()
    first = reg.submit("hh", lambda progress: release.wait(5) and "r")
    with pytest.raises(JobBusyError) as exc:
        reg.submit("other", lambda progress: "r2")
    assert exc.value.active_id == first["id"]
    release.set()
    _wait(reg, first["id"])
    second = reg.submit("other", lambda progress: "r2")
    assert _wait(reg, second["id"])["run_id"] == "r2"


def test_a_failing_job_records_its_error_and_frees_the_worker():
    reg = JobRegistry()

    def boom(progress):
        raise ValueError("no eligible pair")

    job = _wait(reg, reg.submit("hh", boom)["id"])
    assert job["status"] == "failed" and job["error"] == "no eligible pair"
    assert job["run_id"] is None and reg.active() is None


def test_shutdown_interrupts_at_the_next_progress_report_and_joins():
    reg = JobRegistry()
    started = threading.Event()
    reached_end = []

    def long(progress):
        started.set()
        for i in range(1000):
            progress("monte_carlo", i, 1000)
            time.sleep(0.01)
        reached_end.append(True)
        return "never"

    job = reg.submit("hh", long)
    assert started.wait(5)
    reg.shutdown(timeout=5)
    final = reg.get(job["id"])
    assert final["status"] == "failed" and final["error"].startswith("interrupted")
    assert not reached_end


def test_unknown_ids_are_none():
    assert JobRegistry().get("nope") is None


def test_saving_finished_results_is_not_interrupted_by_shutdown():
    reg = JobRegistry()
    computed = threading.Event()
    release = threading.Event()

    def work(progress):
        progress("sensitivity", 4, 4)
        computed.set()
        release.wait(5)
        progress("prepare", 0, 1)  # the stop is already set: must not raise
        return "saved-run"

    job = reg.submit("hh", work)
    assert computed.wait(5)
    stopper = threading.Thread(target=reg.shutdown, kwargs={"timeout": 5})
    stopper.start()
    time.sleep(0.05)
    release.set()
    stopper.join()
    final = reg.get(job["id"])
    assert final["status"] == "done" and final["run_id"] == "saved-run"
    assert final["phase"] == "prepare"


def test_shutdown_reports_a_worker_that_outlasts_the_wait():
    """A job between progress reports cannot be interrupted; shutdown must
    say it is still running rather than return as if it had stopped."""
    reg = JobRegistry()
    started = threading.Event()
    release = threading.Event()

    def stuck(progress):
        started.set()
        release.wait(5)  # a long computation with no progress report
        return "late-run"

    job = reg.submit("hh", stuck)
    assert started.wait(5)
    assert reg.shutdown(timeout=0.05) is False
    assert reg.get(job["id"])["status"] == "running"
    release.set()
    assert reg.shutdown(timeout=5) is True
    assert reg.get(job["id"])["status"] == "done"


def test_shutdown_with_no_job_reports_stopped():
    assert JobRegistry().shutdown(timeout=0) is True


def test_the_app_keeps_the_database_open_under_a_running_worker(monkeypatch, tmp_path):
    from functools import partialmethod

    from fastapi.testclient import TestClient
    from src.api.app import create_app
    from src.data.database import Database

    monkeypatch.setattr(JobRegistry, "shutdown", partialmethod(JobRegistry.shutdown, 0.05))
    closed = []
    monkeypatch.setattr(Database, "close", lambda self: closed.append(True))
    started = threading.Event()
    release = threading.Event()
    app = create_app(str(tmp_path / "t.db"))
    with TestClient(app):
        app.state.jobs.submit("hh", lambda progress: (started.set(), release.wait(5))[1])
        assert started.wait(5)
    assert closed == []          # the worker is still running: not closed
    release.set()

    with TestClient(create_app(str(tmp_path / "u.db"))):
        pass
    assert closed == [True]      # nothing running: closed as before
