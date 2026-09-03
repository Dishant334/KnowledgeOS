# app/worker/celery_app.py

from celery import Celery

celery_app = Celery(
    "ingestion_worker",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/0",
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    # bytes don't serialize well as raw JSON in a task arg — see tasks.py,
    # we base64-encode file data before passing it in.
)                       