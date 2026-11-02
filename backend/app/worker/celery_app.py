# app/worker/celery_app.py

import multiprocessing
import os

from celery import Celery

from app.core.config import settings

# macOS/Windows start pool children with "spawn", not "fork". Celery only
# initializes its fast task tracer in a child that was forked, so every task
# would crash with "ValueError: not enough values to unpack (expected 3, got 0)".
# FORKED_BY_MULTIPROCESSING tells spawned children to run Celery's non-fork
# initialization instead. Inherited by the children; Linux (fork) unaffected.
if multiprocessing.get_all_start_methods()[0] != "fork":  # [0] = platform default, no side effects
    os.environ.setdefault("FORKED_BY_MULTIPROCESSING", "1")

celery_app = Celery(
    "ingestion_worker",
    broker=settings.redis_url,
    backend=settings.redis_url,
    # Import task modules when the worker starts; without this the worker
    # registers no tasks ("Received unregistered task 'ingest_file_task'").
    include=["app.worker.task"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    # bytes don't serialize well as raw JSON in a task arg — see tasks.py,
    # we base64-encode file data before passing it in.
)                       