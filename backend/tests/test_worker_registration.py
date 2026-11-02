"""
Celery task registration — UNIT test with a MOCKED import.

`app.ingestion.pipeline` is stubbed in sys.modules so importing the task module
doesn't load embedding models or touch Qdrant. This verifies what a real worker
(`celery -A app.worker.celery_app worker`) registers at startup; it does NOT run
an actual worker.
"""

import sys
import types


def test_worker_registers_ingest_task(monkeypatch):
    stub = types.ModuleType("app.ingestion.pipeline")
    stub.ingest_file = lambda *a, **kw: None
    monkeypatch.setitem(sys.modules, "app.ingestion.pipeline", stub)
    monkeypatch.delitem(sys.modules, "app.worker.task", raising=False)

    from app.worker.celery_app import celery_app

    assert "app.worker.task" in celery_app.conf.include

    # Same step the worker performs on startup: import configured task modules.
    celery_app.loader.import_default_modules()

    assert "ingest_file_task" in celery_app.tasks
    task = celery_app.tasks["ingest_file_task"]
    assert task.max_retries == 3
    assert task.default_retry_delay == 30


def test_broker_and_backend_come_from_settings():
    """Settings are built at import, so check in a fresh interpreter with REDIS_URL overridden."""
    import os
    import subprocess

    from tests.conftest import BACKEND_DIR

    env = {**os.environ, "REDIS_URL": "redis://example:6390/2", "PYTHONDONTWRITEBYTECODE": "1"}
    out = subprocess.run(
        [sys.executable, "-c",
         "from app.worker.celery_app import celery_app as c; print(c.conf.broker_url, c.conf.result_backend)"],
        cwd=BACKEND_DIR, env=env, capture_output=True, text=True, check=True,
    ).stdout.split()
    assert out == ["redis://example:6390/2", "redis://example:6390/2"]
