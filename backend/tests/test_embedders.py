"""
Dense embedder tests.

- UNIT (mocked fastembed): prefix asymmetry + batch size passthrough.
- INTEGRATION (real bge-large-en-v1.5 via fastembed, ~1.2 GB download on first
  run): dimensions, normalization, relevance ordering. Skipped if the model
  can't be loaded (e.g. offline).
"""

import math

import numpy as np
import pytest

from app.ingestion.embedding import embedders
from app.ingestion.embedding.models import EmbeddingConfig
from app.ingestion.embedding.vector_store import DENSE_DIM


class _FakeTextEmbedding:
    calls: list = []
    init_kwargs: dict = {}

    def __init__(self, model_name, **kwargs):
        self.model_name = model_name
        _FakeTextEmbedding.init_kwargs = kwargs

    def embed(self, texts, batch_size=None):
        texts = list(texts)
        _FakeTextEmbedding.calls.append((texts, batch_size))
        return [np.ones(3) for _ in texts]


@pytest.fixture
def fake_dense(monkeypatch):
    _FakeTextEmbedding.calls = []
    monkeypatch.setattr(embedders, "TextEmbedding", _FakeTextEmbedding)
    return embedders.BGEM3DenseEmbedder(EmbeddingConfig(batch_size=7))


# --- Unit (mocked) ------------------------------------------------------------


def test_configured_model_is_supported_by_fastembed():
    from fastembed import TextEmbedding

    supported = {m["model"]: m for m in TextEmbedding.list_supported_models()}
    name = EmbeddingConfig().dense_model_name
    assert name in supported, f"{name} not in fastembed catalogue"
    assert supported[name]["dim"] == DENSE_DIM


def test_documents_embedded_without_prefix_and_with_batch_size(fake_dense):
    fake_dense.embed_documents(["alpha", "beta"])
    texts, batch_size = _FakeTextEmbedding.calls[-1]
    assert texts == ["alpha", "beta"]
    assert batch_size == 7


def test_query_gets_bge_instruction_prefix(fake_dense):
    fake_dense.embed_query("vacation policy")
    texts, _ = _FakeTextEmbedding.calls[-1]
    assert texts == ["Represent this sentence for searching relevant passages: vacation policy"]


# --- Integration (real model) --------------------------------------------------


@pytest.fixture(scope="module")
def real_dense():
    try:
        return embedders.BGEM3DenseEmbedder(EmbeddingConfig())
    except Exception as exc:  # offline / download failure
        pytest.skip(f"dense model unavailable: {exc}")


def _cos(a, b):
    return sum(x * y for x, y in zip(a, b)) / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))


def test_real_model_dimensions_and_norm(real_dense):
    [vec] = real_dense.embed_documents(["Employees accrue 20 days of paid vacation per year."])
    assert len(vec) == DENSE_DIM
    assert abs(math.sqrt(sum(x * x for x in vec)) - 1.0) < 1e-3
    assert len(real_dense.embed_query("how many vacation days")) == DENSE_DIM


def test_real_model_ranks_relevant_passage_higher(real_dense):
    relevant, irrelevant = real_dense.embed_documents(
        [
            "Employees accrue 20 days of paid vacation per year.",
            "The cafeteria serves lunch between noon and 2pm.",
        ]
    )
    q = real_dense.embed_query("How many vacation days do employees get?")
    assert _cos(q, relevant) > _cos(q, irrelevant)


# --- Sparse (BM25) ---------------------------------------------------------------


class _FakeSparseResult:
    def __init__(self, indices, values):
        self.indices = np.array(indices)
        self.values = np.array(values)


class _FakeSparseEmbedding:
    calls: list = []
    init_kwargs: dict = {}

    def __init__(self, model_name, **kwargs):
        self.model_name = model_name
        _FakeSparseEmbedding.init_kwargs = kwargs

    def embed(self, texts, batch_size=None):
        texts = list(texts)
        _FakeSparseEmbedding.calls.append(("embed", texts, batch_size))
        return [_FakeSparseResult([1, 2], [1.9, 1.6]) for _ in texts]

    def query_embed(self, query, **kwargs):
        _FakeSparseEmbedding.calls.append(("query_embed", query, None))
        return iter([_FakeSparseResult([1, 2], np.array([1, 1], dtype=np.int32))])


@pytest.fixture
def fake_sparse(monkeypatch):
    _FakeSparseEmbedding.calls = []
    monkeypatch.setattr(embedders, "SparseTextEmbedding", _FakeSparseEmbedding)
    return embedders.BM25SparseEmbedder(EmbeddingConfig(batch_size=5))


def test_sparse_query_uses_query_embed(fake_sparse):
    vec = fake_sparse.embed_query("vacation policy")
    kind, arg, _ = _FakeSparseEmbedding.calls[-1]
    assert kind == "query_embed" and arg == "vacation policy"
    assert vec.indices == [1, 2]
    assert vec.values == [1.0, 1.0] and all(isinstance(v, float) for v in vec.values)


def test_sparse_documents_use_embed_with_batch_size(fake_sparse):
    vecs = fake_sparse.embed_documents(["a doc", "b doc"])
    kind, texts, batch_size = _FakeSparseEmbedding.calls[-1]
    assert kind == "embed" and texts == ["a doc", "b doc"] and batch_size == 5
    assert len(vecs) == 2 and vecs[0].values == [1.9, 1.6]


@pytest.fixture(scope="module")
def real_sparse():
    try:
        return embedders.BM25SparseEmbedder(EmbeddingConfig())
    except Exception as exc:
        pytest.skip(f"sparse model unavailable: {exc}")


def test_real_bm25_query_weights_are_term_presence(real_sparse):
    q = real_sparse.embed_query("vacation vacation policy")
    assert len(q.indices) == 2  # 'vacation' counted once
    assert q.values == [1.0, 1.0]


def test_real_bm25_query_and_document_share_term_indices(real_sparse):
    [doc] = real_sparse.embed_documents(["Our vacation policy grants twenty days."])
    q = real_sparse.embed_query("vacation policy")
    assert set(q.indices) <= set(doc.indices)


# --- model cache directory -----------------------------------------------------------


def test_embedders_pass_cache_dir(monkeypatch):
    monkeypatch.setattr(embedders, "TextEmbedding", _FakeTextEmbedding)
    monkeypatch.setattr(embedders, "SparseTextEmbedding", _FakeSparseEmbedding)
    cfg = EmbeddingConfig(cache_dir="/tmp/kos-models")
    embedders.BGEM3DenseEmbedder(cfg)
    embedders.BM25SparseEmbedder(cfg)
    assert _FakeTextEmbedding.init_kwargs == {"cache_dir": "/tmp/kos-models"}
    assert _FakeSparseEmbedding.init_kwargs == {"cache_dir": "/tmp/kos-models"}


def test_cache_path_setting_reaches_embedding_config():
    """Settings are built at import: check in a fresh interpreter, as .env would provide it."""
    import os
    import subprocess
    import sys

    from tests.conftest import BACKEND_DIR

    env = {**os.environ, "FASTEMBED_CACHE_PATH": "./.fastembed_cache", "PYTHONDONTWRITEBYTECODE": "1"}
    out = subprocess.run(
        [sys.executable, "-c",
         "from app.ingestion.embedding.models import EmbeddingConfig as C; print(C().cache_dir)"],
        cwd=BACKEND_DIR, env=env, capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert out == "./.fastembed_cache"
