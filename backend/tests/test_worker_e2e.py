"""
END-TO-END tests with an ACTUAL Celery worker process.

Real: FastAPI app (app.main) + auth dependency, Postgres (<dev_db>_test),
Redis broker/result backend (DB 15), Celery prefork worker subprocess,
loaders/OCR/cleaning/chunking, fastembed bge-large + BM25, Qdrant
(knowledgeos_test_chunks). Only Clerk's JWKS is replaced by a local test key
(tokens are still verified with RS256).

The worker is started WITHOUT FORKED_BY_MULTIPROCESSING in its environment, so
these tests also prove the macOS spawn-pool fix in app/worker/celery_app.py.
"""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tests.conftest import BACKEND_DIR, TEST_QDRANT_COLLECTION, auth_header, make_token, unique_clerk_id
from tests.test_loaders import make_docx, make_pdf, make_pptx, make_xlsx
from tests.test_ocr_pipeline import make_scanned_pdf

PDF = "application/pdf"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"

HANDBOOK_PAGES = (
    "Employees receive twenty days of paid vacation per year under the leave policy.",
    "Travel must be booked through the approved corporate portal two weeks ahead.",
)


# --- infrastructure ----------------------------------------------------------------


def _services_available():
    import redis
    from qdrant_client import QdrantClient

    from app.core.config import settings

    try:
        redis.Redis.from_url(settings.redis_url).ping()
        QdrantClient(url=settings.qdrant_url).get_collections()
        return True
    except Exception:
        return False


class Worker:
    def __init__(self, log_path: Path):
        self.log_path = log_path
        self.proc = None

    def start(self, concurrency=2, timeout=120):
        import redis

        from app.core.config import settings

        assert settings.redis_url.endswith("/15") and settings.qdrant_collection == TEST_QDRANT_COLLECTION
        redis.Redis.from_url(settings.redis_url).delete("celery")  # stale messages from other tests

        env = {k: v for k, v in os.environ.items() if k != "FORKED_BY_MULTIPROCESSING"}
        env.update(PYTHONDONTWRITEBYTECODE="1", UNSTRUCTURED_DISABLE_NOTICE="1")
        self.log = open(self.log_path, "w")
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "celery", "-A", "app.worker.celery_app", "worker",
             "--pool=prefork", f"--concurrency={concurrency}", "--loglevel=info",
             "-n", f"e2e-{os.getpid()}@%h", "--without-gossip", "--without-mingle"],
            cwd=BACKEND_DIR, env=env, stdout=self.log, stderr=subprocess.STDOUT,
        )
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError(f"worker exited early:\n{self.log_path.read_text()[-3000:]}")
            if " ready." in self.log_path.read_text():
                return self
            time.sleep(0.5)
        raise TimeoutError(f"worker not ready:\n{self.log_path.read_text()[-3000:]}")

    def pool_children(self):
        """Pool worker processes only — NOT billiard's semaphore-tracker helper
        (killing that breaks the main process, which is not what we test)."""
        import psutil

        procs = []
        for p in psutil.Process(self.proc.pid).children(recursive=False):
            try:
                if "semaphore_tracker" not in " ".join(p.cmdline()):
                    procs.append(p)
            except psutil.Error:
                pass
        return procs

    def logs(self) -> str:
        return self.log_path.read_text()

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.send_signal(signal.SIGTERM)
            try:
                self.proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.log.close()


@pytest.fixture(scope="module")
def worker(tmp_path_factory):
    if not _services_available():
        pytest.skip("Redis/Qdrant not available")
    w = Worker(tmp_path_factory.mktemp("worker") / "worker.log").start()
    yield w
    w.stop()


@pytest.fixture(scope="module")
def qdrant():
    from qdrant_client import QdrantClient

    from app.core.config import settings

    return QdrantClient(url=settings.qdrant_url)


@pytest.fixture(autouse=True)
def _clear_test_collection_points(qdrant):
    """conftest truncates tables with RESTART IDENTITY, so document ids are reused
    across tests; clear the test collection's points (never the collection itself,
    the running worker holds it) so earlier tests' vectors can't leak in."""
    from qdrant_client.http.models import Filter, FilterSelector

    if qdrant.collection_exists(TEST_QDRANT_COLLECTION):
        qdrant.delete(TEST_QDRANT_COLLECTION, points_selector=FilterSelector(filter=Filter()), wait=True)
    yield


@pytest.fixture
def user_headers():
    return auth_header(make_token(unique_clerk_id()))


def _upload(client, headers, name, data, content_type):
    resp = client.post("/documents", headers=headers, files={"file": (name, data, content_type)})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _wait(client, headers, doc_id, timeout=240, worker=None):
    deadline = time.time() + timeout
    seen = []
    while time.time() < deadline:
        doc = client.get(f"/documents/{doc_id}", headers=headers).json()
        if not seen or seen[-1] != doc["status"]:
            seen.append(doc["status"])
        if doc["status"] in ("ready", "failed"):
            return doc, seen
        time.sleep(0.3)
    raise TimeoutError(f"doc {doc_id} stuck in {seen}\n{worker.logs()[-3000:] if worker else ''}")


def _points(qdrant, doc_id):
    from app.ingestion.embedding.vector_store import document_points_filter

    if not qdrant.collection_exists(TEST_QDRANT_COLLECTION):
        return []
    points, _ = qdrant.scroll(TEST_QDRANT_COLLECTION, scroll_filter=document_points_filter(doc_id),
                              limit=1000, with_payload=True)
    return points


def _error_message(doc_id):
    from app.db.database import SessionLocal
    from app.db.models import Document

    s = SessionLocal()
    try:
        return s.get(Document, doc_id).error_message
    finally:
        s.close()


# --- tests -------------------------------------------------------------------------------


def test_worker_registered_task_and_uses_spawn_safe_pool(worker):
    logs = worker.logs()
    assert ". ingest_file_task" in logs
    assert worker.pool_children(), "prefork pool has no child processes"


def test_upload_to_ready_with_hybrid_vectors_in_qdrant(client, worker, qdrant, user_headers):
    doc = _upload(client, user_headers, "handbook.pdf", make_pdf(HANDBOOK_PAGES), PDF)
    assert doc["status"] == "pending"

    final, seen = _wait(client, user_headers, doc["id"], worker=worker)
    assert final["status"] == "ready", _error_message(doc["id"])
    assert seen[-1] == "ready"

    points = _points(qdrant, doc["id"])
    assert len(points) >= 2
    for p in points:
        meta = p.payload["metadata"]
        assert meta["document_id"] == str(doc["id"])
        assert meta["doc_type"] == "pdf"
        assert meta["source_name"] == meta["source"] == "handbook.pdf"
        assert meta["embedding_model"] == "BAAI/bge-large-en-v1.5"
        assert meta["created_at"].endswith("Z")
    texts = " ".join(p.payload["page_content"] for p in points)
    assert "vacation" in texts and "portal" in texts

    # Both vector spaces were written (dense 1024 + BM25 sparse).
    [one] = qdrant.retrieve(TEST_QDRANT_COLLECTION, ids=[points[0].id], with_vectors=True)
    assert len(one.vector["dense"]) == 1024
    assert len(one.vector["sparse"].indices) > 0


def test_indexed_chunks_are_retrievable_with_user_filter(client, worker, qdrant, user_headers):
    from app.ingestion.embedding.models import EmbeddingConfig
    from app.ingestion.embedding.vector_store import get_vector_store
    from app.retrieval.filters import build_qdrant_filter

    doc = _upload(client, user_headers, "leave.pdf",
                  make_pdf(("Parental leave lasts sixteen weeks at full pay for all staff.",
                            "Sick leave requires a doctor's note after three consecutive days.")), PDF)
    final, _ = _wait(client, user_headers, doc["id"], worker=worker)
    assert final["status"] == "ready", _error_message(doc["id"])
    uploaded_by = _points(qdrant, doc["id"])[0].payload["metadata"]["uploaded_by"]

    store = get_vector_store(EmbeddingConfig())  # same hybrid store config the worker used
    hits = store.similarity_search("how long is parental leave?", k=3,
                                   filter=build_qdrant_filter(uploaded_by=uploaded_by))
    assert hits and all(h.metadata["uploaded_by"] == uploaded_by for h in hits)
    assert "sixteen weeks" in hits[0].page_content

    other_user = store.similarity_search("parental leave", k=3, filter=build_qdrant_filter(uploaded_by="nobody"))
    assert other_user == []


def test_multiple_formats_reach_ready(client, worker, qdrant, user_headers):
    uploads = [
        ("policy.docx", make_docx("Remote work is allowed three days per week with manager approval."), DOCX),
        ("staff.xlsx", make_xlsx(), XLSX),
        ("deck.pptx", make_pptx(), PPTX),
        ("notes.md", b"# Notes\n\nThe office closes at six on Fridays for maintenance.", "text/markdown"),
    ]
    ids = [_upload(client, user_headers, *u)["id"] for u in uploads]
    for doc_id, (name, _, _) in zip(ids, uploads):
        final, _ = _wait(client, user_headers, doc_id, worker=worker)
        assert final["status"] == "ready", (name, _error_message(doc_id))
        assert _points(qdrant, doc_id), name


def test_scanned_pdf_is_ocred_by_worker(client, worker, qdrant, user_headers):
    doc = _upload(client, user_headers, "scan.pdf", make_scanned_pdf("Scanned invoice total amount due"), PDF)
    final, _ = _wait(client, user_headers, doc["id"], worker=worker)
    assert final["status"] == "ready", _error_message(doc["id"])
    points = _points(qdrant, doc["id"])
    assert any("invoice" in p.payload["page_content"].lower() for p in points)
    assert all(p.payload["metadata"].get("ocr_used") for p in points)


def test_corrupt_file_fails_with_persisted_error(client, worker, qdrant, user_headers):
    doc = _upload(client, user_headers, "broken.pdf", b"%PDF-1.4\nthis is not really a pdf", PDF)
    final, seen = _wait(client, user_headers, doc["id"], worker=worker)
    assert final["status"] == "failed"
    assert "processing" in seen or seen[0] == "pending"
    assert _error_message(doc["id"])
    assert _points(qdrant, doc["id"]) == []


def test_duplicate_dispatch_processes_once(client, worker, qdrant, user_headers):
    from app.worker.celery_app import celery_app

    doc = _upload(client, user_headers, "dup.pdf", make_pdf(("Duplicate delivery test about vacation policy.",)), PDF)
    # Two extra deliveries of the same document (concurrency=2 -> genuinely parallel).
    extra = [celery_app.send_task("ingest_file_task", args=[doc["id"]]) for _ in range(2)]
    final, _ = _wait(client, user_headers, doc["id"], worker=worker)
    assert final["status"] == "ready", _error_message(doc["id"])

    results = [r.get(timeout=240) for r in extra]
    assert any(r.get("skipped") in ("in_progress", "already_ready") for r in results), results
    points = _points(qdrant, doc["id"])
    chunk_ids = {p.payload["metadata"]["chunk_index"] for p in points}
    assert len(points) == len(chunk_ids)  # no duplicated chunks


def test_delete_removes_vectors_after_worker_indexing(client, worker, qdrant, user_headers):
    doc = _upload(client, user_headers, "gone.pdf", make_pdf(("This document will be deleted shortly.",)), PDF)
    final, _ = _wait(client, user_headers, doc["id"], worker=worker)
    assert final["status"] == "ready" and _points(qdrant, doc["id"])

    assert client.delete(f"/documents/{doc['id']}", headers=user_headers).status_code == 204
    assert _points(qdrant, doc["id"]) == []
    assert client.get(f"/documents/{doc['id']}", headers=user_headers).status_code == 404


def test_worker_process_killed_mid_task_is_recovered(client, worker, qdrant, user_headers):
    """SIGKILL the pool child while it processes -> message requeued (acks_late +
    reject_on_worker_lost) -> a fresh child finishes the document."""
    import psutil

    words = ("travel expense receipt claim approval manager budget invoice vendor contract policy "
             "reimbursement mileage lodging per diem audit compliance quarter fiscal ledger").split()
    pages = tuple(
        " ".join(f"{words[(i * 7 + j) % len(words)]}{j}" for j in range(450)) for i in range(300)
    )  # ~300 pages of distinct text: long enough to kill mid-processing
    doc = _upload(client, user_headers, "big.pdf", make_pdf(pages), PDF)

    deadline = time.time() + 120
    while client.get(f"/documents/{doc['id']}", headers=user_headers).json()["status"] != "processing":
        assert time.time() < deadline, worker.logs()[-2000:]
        time.sleep(0.05)
    killed = [p.pid for p in worker.pool_children() if p.is_running()]
    for pid in killed:
        os.kill(pid, signal.SIGKILL)

    final, _ = _wait(client, user_headers, doc["id"], timeout=300, worker=worker)
    assert final["status"] == "ready", (_error_message(doc["id"]), worker.logs()[-3000:])
    assert "WorkerLostError" in worker.logs() or "signal 9" in worker.logs()
    points = _points(qdrant, doc["id"])
    assert len(points) == len({p.payload["metadata"]["chunk_index"] for p in points}) > 0
    assert all(not psutil.pid_exists(pid) or psutil.Process(pid).status() == psutil.STATUS_ZOMBIE for pid in killed)
