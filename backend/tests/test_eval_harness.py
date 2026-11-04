"""
The evaluation harness (backend/eval/) must itself be trustworthy: a wrong metric is worse than none.

  1. DATA          the golden set agrees with the generated documents (the ground truth is real)
  2. EXACT METRICS hand-computed expectations
  3. REPORT        aggregation and rendering
  4. SAFETY        the harness cannot touch the production collection; tracing is opt-in
  5. PIPELINE      the real ingestion + retrieval + generation code on the evaluation corpus
  6. RAGAS         the library works with our wiring (real local judge, auto-skipped without Ollama)
"""

import json
import os
import re
import subprocess
import sys

import pymupdf
import pytest

from eval.compat import install_ragas_compat
from eval.corpus import DOCS, build_corpus
from eval.metrics import answer_metrics, is_relevant, load_golden_set, mean, normalise, percentile, retrieval_metrics
from eval.pipelines import CONFIG_NAMES
from eval.report import render_markdown, summarise_config
from tests.conftest import BACKEND_DIR, make_fake_llm
from tests.test_llm import needs_ollama


def ctx(source, text):
    return {"source": source, "text": text, "page": None, "score": None}


# --- 1. data --------------------------------------------------------------------------------------------


def readable_text(document) -> str:
    """The text as the real loaders will see it (PDFs are read back from the generated file)."""
    if document.kind == "pdf":
        return " ".join(page.get_text() for page in pymupdf.open(stream=document.data, filetype="pdf"))
    return document.text


def test_every_golden_passage_exists_in_the_document_it_points_to():
    documents = {d.filename: d for d in build_corpus()}
    for gold in load_golden_set():
        for expected in gold["expected"]:
            assert expected["doc"] in documents, (gold["id"], expected["doc"])
            assert normalise(expected["passage"]) in normalise(readable_text(documents[expected["doc"]])), (gold["id"], expected)


def test_golden_set_is_well_formed():
    golden = load_golden_set()
    ids = [g["id"] for g in golden]
    assert len(ids) == len(set(ids)) >= 40
    assert {g["type"] for g in golden} == {"direct", "paraphrase", "distractor", "multi", "out_of_scope"}
    for g in golden:
        assert g["question"].strip() and g["reference"].strip()
        assert g["answerable"] == (g["type"] != "out_of_scope")
        if g["answerable"]:
            assert g["expected"] and re.compile(g["answer_regex"])
            # the golden answer itself must satisfy its own answer pattern
            assert re.search(g["answer_regex"], g["reference"], re.IGNORECASE), g["id"]
        else:
            assert g["expected"] == [] and g["answer_regex"] is None
    assert all(len(g["expected"]) == 2 for g in golden if g["type"] == "multi")


def test_corpus_is_big_enough_to_make_retrieval_non_trivial():
    documents = build_corpus()
    assert len(documents) == len(DOCS) == 13
    assert {d.kind for d in documents} == {"md", "txt", "html", "pdf", "docx"}
    assert sum(len(d.data) for d in documents) > 80_000          # long enough that documents split into many chunks


def test_corpus_is_deterministic():
    """Same documents every time (PDFs embed a creation timestamp, so compare what they say, not their bytes)."""
    first, second = build_corpus(), build_corpus()
    assert [d.filename for d in first] == [d.filename for d in second]
    assert [normalise(readable_text(d)) for d in first] == [normalise(readable_text(d)) for d in second]
    assert [d.data for d in first if d.kind != "pdf"] == [d.data for d in second if d.kind != "pdf"]


def test_distractor_documents_really_are_near_duplicates():
    texts = {d.filename: d.text for d in build_corpus()}
    europe, us = texts["travel_policy_europe.pdf"], texts["travel_policy_us.pdf"]
    assert "EUR 75" in europe and "$85" in us and "EUR 75" not in us and "$85" not in europe


# --- 2. exact metrics ----------------------------------------------------------------------------------------


def test_relevance_needs_the_right_document_and_the_sentence():
    req = {"doc": "a.md", "passage": "25 days of vacation"}
    assert is_relevant(ctx("a.md", "Staff get  25 DAYS of\nvacation each year"), req) is True        # line breaks, extra spaces and case do not matter
    assert is_relevant(ctx("a.md", "Staff get 25 days of paid vacation"), req) is False                # different words in between: not the sentence
    assert is_relevant(ctx("b.md", "Staff get 25 days of vacation"), req) is False                      # right text, wrong document


def test_retrieval_metrics_single_passage():
    req = [{"doc": "a.md", "passage": "needle"}]
    contexts = [ctx("a.md", "hay"), ctx("a.md", "hay needle hay"), ctx("a.md", "hay"), ctx("a.md", "hay"), ctx("a.md", "hay")]
    m = retrieval_metrics(contexts, req)
    assert m == {"recall": 1.0, "hit": 1.0, "precision": 0.2, "mrr": 0.5}      # found at rank 2


def test_retrieval_metrics_partial_and_missing():
    two = [{"doc": "a.md", "passage": "one"}, {"doc": "b.md", "passage": "two"}]
    assert retrieval_metrics([ctx("a.md", "one"), ctx("c.md", "x")], two) == {"recall": 0.5, "hit": 0.0, "precision": 0.5, "mrr": 1.0}
    assert retrieval_metrics([ctx("c.md", "nothing")], two) == {"recall": 0.0, "hit": 0.0, "precision": 0.0, "mrr": 0.0}
    assert retrieval_metrics([], two)["precision"] == 0.0
    assert retrieval_metrics([ctx("a.md", "x")], []) is None                    # out-of-scope questions have no expected passage


def test_retrieval_metrics_only_look_at_the_top_k():
    req = [{"doc": "a.md", "passage": "needle"}]
    contexts = [ctx("a.md", "hay")] * 5 + [ctx("a.md", "needle")]              # the right chunk is 6th
    assert retrieval_metrics(contexts, req, k=5)["hit"] == 0.0
    assert retrieval_metrics(contexts, req, k=6)["hit"] == 1.0


GOLD = {"answerable": True, "expected": [{"doc": "a.md", "passage": "x"}], "answer_regex": r"\b25\b|twenty[- ]five"}


def sample(answer, abstained=False, cited=("a.md",)):
    return {"answer": answer, "abstained": abstained, "cited_sources": list(cited)}


def test_answer_metrics_for_answerable_questions():
    assert answer_metrics(sample("You get 25 days [1]."), GOLD) == {"correct": 1.0, "false_abstention": 0.0, "citation_hit": 1.0, "citation_precision": 1.0}
    wrong = answer_metrics(sample("You get 30 days [1]."), GOLD)
    assert wrong["correct"] == 0.0 and wrong["false_abstention"] == 0.0
    refused = answer_metrics(sample("I don't have enough information.", abstained=True, cited=()), GOLD)
    assert refused["correct"] == 0.0 and refused["false_abstention"] == 1.0 and refused["citation_precision"] is None
    mixed = answer_metrics(sample("25 days [1][2]", cited=("a.md", "b.md")), GOLD)
    assert mixed["citation_hit"] == 1.0 and mixed["citation_precision"] == 0.5
    assert answer_metrics(sample("25 days", cited=("b.md",)), GOLD)["citation_hit"] == 0.0


def test_answer_metrics_for_out_of_scope_questions():
    gold = {"answerable": False, "expected": [], "answer_regex": None}
    assert answer_metrics(sample("I don't have enough information.", abstained=True, cited=()), gold) == {"correct": 1.0}
    assert answer_metrics(sample("The CEO earns a lot.", cited=("a.md",)), gold) == {"correct": 0.0}          # invented answer
    assert answer_metrics(sample("I don't know.", abstained=True, cited=("a.md",)), gold) == {"correct": 0.0}  # refused but cited


def test_mean_and_percentile_ignore_missing_values():
    assert mean([1.0, None, float("nan"), 3.0]) == 2.0
    assert mean([None, float("nan")]) is None and mean([]) is None
    assert percentile([5, 1, 3, 2, 4], 0.5) == 3 and percentile([1], 0.95) == 1 and percentile([], 0.5) is None


# --- 3. report --------------------------------------------------------------------------------------------------


def make_sample(qid, answer, contexts, abstained=False, cited=("a.md",)):
    return {"id": qid, "answer": answer, "abstained": abstained, "cited_sources": list(cited), "contexts": contexts,
            "retrieval_ms": 100.0, "generation_ms": 2000.0, "tokens": 500, "question": "q", "reference": "r", "type": "direct", "config": "c"}


def test_summarise_config_and_render():
    golden = {
        "q1": {**GOLD, "id": "q1", "type": "direct"},
        "q2": {**GOLD, "id": "q2", "type": "paraphrase", "expected": [{"doc": "a.md", "passage": "missing"}]},
        "q3": {"id": "q3", "type": "out_of_scope", "answerable": False, "expected": [], "answer_regex": None},
    }
    samples = [
        make_sample("q1", "25 days", [ctx("a.md", "x")]),
        make_sample("q2", "25 days", [ctx("a.md", "nothing here")]),
        make_sample("q3", "I don't know", [], abstained=True, cited=()),
    ]
    ragas = {"q1": {"id": "q1", "faithfulness": 1.0, "answer_relevancy": 0.8, "context_precision": 1.0, "context_recall": None},
             "q2": {"id": "q2", "faithfulness": 0.5, "answer_relevancy": 0.6, "context_precision": 0.0, "context_recall": 1.0}}

    summary = summarise_config(samples, golden, ragas)

    assert summary["hit@5"] == 0.5 and summary["mrr"] == 0.5 and summary["answer_correct"] == 1.0
    assert summary["refuses_out_of_scope"] == 1.0
    assert summary["hit@5_by_type"] == {"direct": (1.0, 1), "paraphrase": (0.0, 1)}
    assert summary["ragas_faithfulness"] == 0.75 and summary["ragas_context_recall"] == 1.0
    assert summary["ragas_context_recall_valid"] == "1/2"                    # the failed judge call is visible, not hidden
    assert summary["generation_s_p50"] == 2.0 and summary["tokens_per_question"] == 500

    info = {"date": "2026-11-04", "questions": 3, "answerable": 2, "documents": 13, "chunks": 26, "generator": "g", "judge": "j",
            "embedder": "e", "reranker": "r"}
    markdown = render_markdown({"hybrid": summary, "dense": summary}, info)
    for text in ("# RAG evaluation report", "| metric | hybrid | dense |", "Hit@5", "Faithfulness", "Hit@5 by question type", "paraphrase (1)"):
        assert text in markdown
    assert "RAGAS (LLM-as-judge" not in render_markdown({"x": summarise_config(samples, golden, None)}, info)   # no RAGAS section without scores


# --- 4. safety -------------------------------------------------------------------------------------------------------


def run_python(code, **env):
    return subprocess.run([sys.executable, "-W", "ignore", "-c", code], cwd=BACKEND_DIR, text=True, capture_output=True, timeout=180,
                          env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", **env})


def test_the_harness_refuses_to_run_on_the_production_collection():
    result = run_python("from eval.ingest import ingest_corpus\ningest_corpus()", QDRANT_COLLECTION="documents")
    assert result.returncode != 0 and "production collection" in result.stderr


def test_tracing_is_off_unless_requested():
    from eval.run import configure_environment, parse_args

    old = os.environ.get("LANGSMITH_TRACING")
    try:
        configure_environment(parse_args(["--no-ragas"]))
        assert os.environ["LANGSMITH_TRACING"] == "false"
        configure_environment(parse_args(["--trace"]))
        assert os.environ["LANGSMITH_TRACING"] == "true"
    finally:
        os.environ["LANGSMITH_TRACING"] = old or "false"


def test_cli_defaults():
    from eval.run import parse_args

    args = parse_args([])
    assert args.configs == CONFIG_NAMES and not args.no_ragas and args.generator == "ollama" and args.judge == "ollama"


# --- 5. the real pipeline on the evaluation corpus ----------------------------------------------------------------------


@pytest.fixture(scope="module")
def ingested():
    """Ingest the evaluation corpus once (real ingestion code) into the isolated TEST collection."""
    from app.ingestion.embedding.models import EmbeddingConfig
    from app.ingestion.embedding.vector_store import get_qdrant_client
    from app.ingestion.pipeline import get_embedding_orchestrator
    from app.retrieval.orchestrator import get_search_store
    from eval.ingest import ingest_corpus

    config = EmbeddingConfig()
    client = get_qdrant_client(config)
    try:
        client.get_collections()
    except Exception as exc:
        pytest.skip(f"Qdrant unavailable: {exc}")
    get_embedding_orchestrator.cache_clear()
    get_search_store.cache_clear()
    info = ingest_corpus(reset=True)
    yield info
    get_search_store.cache_clear()
    if client.collection_exists(config.collection_name):
        client.delete_collection(config.collection_name)


def test_corpus_ingests_into_many_chunks(ingested):
    assert ingested["documents"] == 13
    assert ingested["chunks"] >= 50                                          # many chunks per document: retrieval has real work to do
    assert all(count >= 2 for count in ingested["chunks_per_document"].values())


@pytest.mark.parametrize("config", CONFIG_NAMES)
def test_every_configuration_produces_a_complete_sample(ingested, config):
    from eval.pipelines import run_question

    gold = next(g for g in load_golden_set() if g["id"] == "q01")
    result = run_question(config, gold, make_fake_llm(answer="Employees accrue 25 days [1]."))

    assert result["config"] == config and result["id"] == "q01"
    assert 1 <= len(result["contexts"]) <= 5
    assert all({"text", "source", "page", "score"} <= set(c) for c in result["contexts"])
    assert result["answer"] == "Employees accrue 25 days [1]." and result["cited_sources"]
    assert result["retrieval_ms"] > 0 and result["generation_ms"] >= 0 and isinstance(result["tokens"], int)
    json.dumps(result)                                                       # samples must be saveable as JSON


@pytest.mark.parametrize("config", CONFIG_NAMES)
def test_each_configuration_finds_an_easy_fact(ingested, config):
    from eval.pipelines import retrieve_chunks, describe

    gold = next(g for g in load_golden_set() if g["id"] == "q01")
    metrics = retrieval_metrics(describe(retrieve_chunks(config, gold["question"])), gold["expected"])
    assert metrics["hit"] == 1.0, f"{config} missed the vacation-days sentence"


def test_the_distractor_questions_get_the_right_travel_document(ingested):
    from eval.pipelines import describe, retrieve_chunks

    by_id = {g["id"]: g for g in load_golden_set()}
    for qid, expected_doc in (("q30", "travel_policy_europe.pdf"), ("q31", "travel_policy_us.pdf")):
        top = describe(retrieve_chunks("hybrid+rerank", by_id[qid]["question"]))
        assert top[0]["source"] == expected_doc, qid


@needs_ollama
def test_the_runner_end_to_end_without_ragas(ingested, tmp_path):
    from eval.run import main

    out_dir = main(["--limit", "4", "--configs", "hybrid", "hybrid+rerank", "--no-ragas", "--skip-ingest", "--reuse", str(tmp_path)])

    report = (out_dir / "report.md").read_text()
    assert "# RAG evaluation report" in report and "| metric | hybrid | hybrid+rerank |" in report
    summary = json.loads((out_dir / "summary.json").read_text())
    assert summary["hybrid"]["hit@5"] == 1.0 and summary["hybrid"]["answer_correct"] == 1.0
    assert len(json.loads((out_dir / "samples_hybrid.json").read_text())) == 4


# --- 6. RAGAS ----------------------------------------------------------------------------------------------------------


def test_ragas_imports_with_the_compatibility_shim():
    install_ragas_compat()
    install_ragas_compat()                                                   # safe to call twice
    import ragas
    from ragas.metrics import answer_relevancy, context_precision, context_recall, faithfulness

    assert ragas.__version__ and all((faithfulness, answer_relevancy, context_precision, context_recall))


def test_ragas_dataset_has_the_four_fields_it_needs():
    from eval.ragas_scoring import build_dataset

    dataset = build_dataset([{"id": "x", "question": "q?", "contexts": [{"text": "c1"}, {"text": "c2"}], "answer": "a", "reference": "r"}])
    row = dataset.to_list()[0]
    assert row["user_input"] == "q?" and row["retrieved_contexts"] == ["c1", "c2"] and row["response"] == "a" and row["reference"] == "r"


def test_scoring_nothing_is_a_no_op():
    from eval.ragas_scoring import score_samples

    assert score_samples([], judge=None, embeddings=None) == []


@needs_ollama
def test_ragas_separates_a_faithful_answer_from_a_hallucinated_one():
    """The core promise of the faithfulness metric, checked with the real local judge (model-dependent: needs margin, not exact values)."""
    from eval.ragas_scoring import make_embeddings, make_judge, score_samples

    contexts = [{"text": "Meals are reimbursed up to $60 per day while travelling."}, {"text": "Flights must be booked in economy class."}]
    samples = [
        {"id": "honest", "question": "What is the daily meal limit?", "contexts": contexts, "answer": "Meals are reimbursed up to $60 per day [1].", "reference": "Meals are reimbursed up to $60 per day."},
        {"id": "invented", "question": "What is the daily meal limit?", "contexts": contexts, "answer": "Meals are reimbursed up to $100 per day and alcohol is included [1].", "reference": "Meals are reimbursed up to $60 per day."},
    ]
    scores = {s["id"]: s for s in score_samples(samples, make_judge("ollama"), make_embeddings(), max_workers=2)}

    assert scores["honest"]["faithfulness"] is not None and scores["invented"]["faithfulness"] is not None
    assert scores["honest"]["faithfulness"] > scores["invented"]["faithfulness"]
    for row in scores.values():
        for name in ("faithfulness", "answer_relevancy", "context_precision", "context_recall"):
            assert row[name] is None or 0.0 <= row[name] <= 1.0
