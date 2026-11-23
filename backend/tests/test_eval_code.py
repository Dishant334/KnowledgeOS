# CODEBASE-FEATURE (Stage 5/6): the CODE evaluation, which lives in its own package `eval_code/` (separate from the
# documents evaluation in `eval/`; these tests do not import or touch that one or its tests).
#
# 1. DATA        the frozen corpus and the golden set agree with each other (the ground truth is real)  - unit
# 2. SEPARATION  the code evaluation imports nothing from the documents evaluation                      - unit
# 3. METRICS     the "cites the right lines" metric and the report rows                                 - unit
# 4. COMPARE     the side-by-side comparison of runs (reference column, deltas, flipped questions)      - unit
# 5. FAIRNESS    every expected passage survives chunking whole, in a chunk whose lines cover it        - real chunker
# 6. CLI         --split / --tag / chunker flags, and the protected collections are refused             - unit/subprocess
# 7. PIPELINE    the real configurations on the code corpus (real Qdrant + models)                      - integration
import hashlib
import json
import os
import re
import subprocess
import sys
from collections import Counter

import pytest
from langchain_core.documents import Document

from app.ingestion.loaders.code_loader import CODE_MIME_TYPE
from app.retrieval.model import ScoredChunk
from eval_code.metrics import answer_metrics, is_relevant
from eval_code.pipelines import CONFIG_NAMES
from eval_code.suite import (
    CORPUS_DIR,
    MANIFEST_NAME,
    build_corpus,
    corpus_paths,
    corpus_text,
    find_passage,
    load_golden_set,
    passage_lines,
)
from tests.conftest import BACKEND_DIR
from tests.test_llm import needs_ollama

ALL = load_golden_set()


def run_python(code: str, **env):
    """Runs a snippet in a fresh process (settings are read once at import, so some checks need their own process)."""
    return subprocess.run([sys.executable, "-W", "ignore", "-c", code], cwd=BACKEND_DIR, text=True, capture_output=True, timeout=180,
                          env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", **env})


# --- 1. the corpus and the golden set -----------------------------------------------------------------------------------


def test_the_corpus_is_the_24_frozen_source_files_of_both_languages():
    files = build_corpus()
    names = [f.filename for f in files]
    assert len(files) == 24 and len(set(names)) == 24
    assert all(f.kind == "code" and f.mime == CODE_MIME_TYPE for f in files)
    assert {n.rsplit(".", 1)[1] for n in names} == {"py", "js"}
    assert all(n.startswith(("backend/", "frontend/")) for n in names)
    assert sum(len(f.text.splitlines()) for f in files) > 2500          # big enough to need many chunks


def test_the_corpus_has_not_drifted_from_its_manifest():
    """The manifest records a hash per file; editing a frozen file makes every golden line number untrustworthy."""
    manifest = (CORPUS_DIR / MANIFEST_NAME).read_text()
    for path in corpus_paths():
        name = path.relative_to(CORPUS_DIR).as_posix()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
        assert f"| `{name}` |" in manifest and f"`{digest}`" in manifest, f"{name} changed after it was frozen"


def test_every_corpus_file_passes_the_project_policy_and_none_looks_like_a_secret():
    from app.ingestion.codebase.policy import TIER_CODE, classify

    for path in corpus_paths():
        verdict = classify(path.relative_to(CORPUS_DIR).as_posix())
        assert verdict.accepted and verdict.tier == TIER_CODE, path


def test_the_golden_set_is_well_formed():
    assert len(ALL) == 25
    assert [g["id"] for g in ALL] == [f"c{n:02d}" for n in range(1, 26)]
    assert len({g["question"] for g in ALL}) == 25
    assert Counter(g["split"] for g in ALL) == {"dev": 17, "test": 8}
    assert Counter(g["type"] for g in ALL) == {"direct": 7, "paraphrase": 5, "distractor": 3, "multi": 3, "global": 3, "out_of_scope": 4}
    for split in ("dev", "test"):                                        # both splits cover every kind of question
        assert {g["type"] for g in ALL if g["split"] == split} == {"direct", "paraphrase", "distractor", "multi", "global", "out_of_scope"}
    for g in ALL:
        assert g["answerable"] == (g["type"] != "out_of_scope")
        re.compile(g["answer_regex"])
        if g["answerable"]:
            assert g["reference"] and re.search(g["answer_regex"], g["reference"], re.IGNORECASE), g["id"]    # the golden answer satisfies its own pattern
            assert g["expected"], g["id"]
        else:
            assert g["expected"] == [] and g["absent_terms"], g["id"]
    assert all(len(g["expected"]) == 1 for g in ALL if g["type"] in ("direct", "paraphrase", "distractor"))
    assert all(len(g["expected"]) >= 2 for g in ALL if g["type"] in ("multi", "global"))
    assert all(len({e["doc"] for e in g["expected"]}) >= 2 for g in ALL if g["type"] == "global")        # global = spread over files


def test_every_expected_passage_is_found_exactly_once_in_its_file():
    for g in ALL:
        for e in g["expected"]:
            assert len(find_passage(corpus_text(e["doc"]), e["passage"])) == 1, (g["id"], e["doc"], e["passage"][:50])
            first, last = e["lines"]
            assert 1 <= first <= last <= len(corpus_text(e["doc"]).splitlines())


def test_out_of_scope_questions_are_really_about_things_the_code_does_not_contain():
    everything = "\n".join(f.text for f in build_corpus())
    for g in ALL:
        for term in g.get("absent_terms", []):
            assert not re.search(r"\b" + re.escape(term) + r"\b", everything, re.IGNORECASE), (g["id"], term)


def test_splits_can_be_selected():
    assert len(load_golden_set("dev")) == 17 and len(load_golden_set("test")) == 8
    assert len(load_golden_set("all")) == len(load_golden_set(None)) == 25
    assert not {g["id"] for g in load_golden_set("dev")} & {g["id"] for g in load_golden_set("test")}


def test_line_numbers_are_computed_from_the_frozen_file_not_typed_by_hand():
    gold = next(g for g in ALL if g["id"] == "c05")              # the sha256 line of hashing.py
    [e] = gold["expected"]
    text_lines = corpus_text(e["doc"]).splitlines()
    assert "sha256" in text_lines[e["lines"][0] - 1]
    assert e["lines"][0] == e["lines"][1]


def test_passage_lines_handles_multi_line_passages_case_and_ambiguity():
    text = "alpha\nbeta gamma\ndelta\nbeta gamma\n"
    assert passage_lines(text, "alpha beta gamma") == (1, 2)             # spans two lines
    assert passage_lines(text, "DELTA") == (3, 3)                        # case does not matter
    assert passage_lines(text, "beta gamma") is None                     # twice: ambiguous
    assert passage_lines(text, "missing") is None


# --- 2. separation from the documents evaluation -----------------------------------------------------------------------------


def test_the_code_evaluation_imports_nothing_from_the_documents_evaluation():
    """The two evaluations must stay independent: changing one can never break or change the other."""
    pattern = re.compile(r"^\s*(?:from\s+eval(?:\.|\s+import)|import\s+eval\b)", re.MULTILINE)
    for path in (BACKEND_DIR / "eval_code").glob("*.py"):
        assert not pattern.search(path.read_text()), f"{path.name} imports the documents evaluation"


def test_the_code_evaluation_has_its_own_data_and_results_folders():
    root = BACKEND_DIR / "eval_code"
    assert (root / "corpus").is_dir() and (root / "golden_set.jsonl").is_file() and (root / "results").is_dir()
    assert not (BACKEND_DIR / "eval" / "code_corpus").exists() and not (BACKEND_DIR / "eval" / "code_golden_set.jsonl").exists()


# --- 3. metrics and report ---------------------------------------------------------------------------------------------


def _gold(lines=((10, 12),), docs=("a.py",)):
    return {"answerable": True, "answer_regex": "x", "expected": [{"doc": d, "passage": "p", "lines": list(l)} for d, l in zip(docs, lines)]}


def _sample(cited, answer="x [1]"):
    return {"answer": answer, "abstained": False, "cited_sources": sorted({c["source"] for c in cited}), "cited": cited}


def cite(source="a.py", start=9, end=13):
    return {"source": source, "file_path": source, "start_line": start, "end_line": end}


def test_a_citation_whose_lines_cover_the_passage_counts():
    result = answer_metrics(_sample([cite(start=9, end=13)]), _gold())
    assert result["citation_hit"] == 1.0 and result["citation_line_hit"] == 1.0 and result["citation_line_precision"] == 1.0


def test_a_citation_that_only_overlaps_the_passage_still_counts():
    assert answer_metrics(_sample([cite(start=12, end=30)]), _gold())["citation_line_hit"] == 1.0


def test_right_file_wrong_lines_is_not_a_line_hit():
    result = answer_metrics(_sample([cite(start=40, end=60)]), _gold())
    assert result["citation_hit"] == 1.0 and result["citation_line_hit"] == 0.0 and result["citation_line_precision"] == 0.0


def test_right_lines_in_the_wrong_file_is_not_a_line_hit():
    result = answer_metrics(_sample([cite(source="b.py", start=10, end=12)]), _gold())
    assert result["citation_hit"] == 0.0 and result["citation_line_hit"] == 0.0


def test_line_precision_is_the_fraction_of_citations_on_target():
    result = answer_metrics(_sample([cite(start=10, end=12), cite(start=80, end=90)]), _gold())
    assert result["citation_line_hit"] == 1.0 and result["citation_line_precision"] == 0.5


def test_a_citation_without_line_numbers_is_not_a_line_hit_and_does_not_crash():
    result = answer_metrics(_sample([{"source": "a.py", "file_path": "a.py", "start_line": None, "end_line": None}]), _gold())
    assert result["citation_hit"] == 1.0 and result["citation_line_hit"] == 0.0


def test_no_citations_at_all():
    result = answer_metrics(_sample([]), _gold())
    assert result["citation_line_hit"] == 0.0 and result["citation_line_precision"] is None


def test_the_report_shows_the_line_rows_the_chunker_and_the_split():
    from eval_code.report import render_markdown, summarise_config

    golden = {"q": {"id": "q", "type": "direct", "answerable": True, "answer_regex": "x", "question": "?", "reference": "x",
                    "expected": [{"doc": "a.py", "passage": "p", "lines": [10, 12]}]}}
    contexts = [{"text": "p", "source": "a.py", "page": None, "score": 1.0}]
    sample = {"id": "q", "contexts": contexts, "contexts_used": contexts, "answer": "x", "abstained": False, "cited_sources": ["a.py"],
              "cited": [cite(start=9, end=13)], "retrieval_ms": 5.0, "generation_ms": 900.0, "tokens": 100}
    summary = summarise_config([sample], golden, None)
    assert summary["citation_line_hit"] == 1.0
    info = {"date": "d", "questions": 1, "answerable": 1, "documents": 24, "chunks": 85, "generator": "g", "judge": "none",
            "embedder": "e", "reranker": "r", "split": "dev", "chunking": "ast, header off"}
    report = render_markdown({"hybrid": summary}, info)
    assert "# Code RAG evaluation report" in report and "Cites the expected file AND its lines" in report
    assert "split: dev" in report and "chunking: ast, header off" in report and "24 source files" in report


def test_describe_carries_the_file_path_and_lines_of_each_chunk():
    from eval_code.pipelines import describe

    chunk = ScoredChunk(Document(page_content="x", metadata={"source_name": "a.py", "file_path": "a.py", "start_line": 3, "end_line": 9}), fused_score=0.5)
    [d] = describe([chunk])
    assert (d["file_path"], d["start_line"], d["end_line"]) == ("a.py", 3, 9)


# --- 4. the comparison ---------------------------------------------------------------------------------------------------------


def _fake_run(tmp_path, name, hits, correct, chunking="splitter, header off", chunks=85, ragas=None):
    """A finished run folder with one configuration and two questions (c01 direct, c13 global)."""
    folder = tmp_path / name
    folder.mkdir()
    gold = {g["id"]: g for g in ALL}
    samples = []
    for qid, hit, ok in zip(("c01", "c13"), hits, correct):
        expected = gold[qid]["expected"]
        contexts = [{"text": e["passage"], "source": e["doc"], "page": None, "score": 1.0} for e in expected] if hit else \
                   [{"text": "unrelated", "source": "other.py", "page": None, "score": 0.1}]
        samples.append({"id": qid, "type": gold[qid]["type"], "config": "hybrid+rerank", "question": gold[qid]["question"],
                        "reference": gold[qid]["reference"], "contexts": contexts, "contexts_used": contexts,
                        "answer": "token bucket 20 MB document.py files.js" if ok else "I don't know", "abstained": not ok,
                        "cited_sources": [], "cited": [], "retrieval_ms": 10.0, "generation_ms": 1000.0, "tokens": 100})
    (folder / "samples_hybrid+rerank.json").write_text(json.dumps(samples))
    (folder / "meta.json").write_text(json.dumps({"chunking": chunking, "judge": "ollama (qwen3:8b)", "commit": "abc1234"}))
    (folder / "corpus.json").write_text(json.dumps({"documents": 24, "chunks": chunks}))
    if ragas:
        (folder / "ragas_hybrid+rerank.json").write_text(json.dumps([{"id": "c01", **ragas}, {"id": "c13", **ragas}]))
    return folder


RAGAS_LOW = {"faithfulness": 0.5, "answer_relevancy": 0.6, "context_precision": 0.4, "context_recall": 0.5}
RAGAS_HIGH = {"faithfulness": 0.9, "answer_relevancy": 0.8, "context_precision": 0.7, "context_recall": 0.8}


def test_the_comparison_has_a_reference_column_deltas_ragas_and_the_flipped_questions(tmp_path):
    from eval_code.compare import main

    base = _fake_run(tmp_path, "base", hits=(1, 0), correct=(1, 0), ragas=RAGAS_LOW)
    better = _fake_run(tmp_path, "ast", hits=(1, 1), correct=(1, 1), chunking="ast, header off", chunks=60, ragas=RAGAS_HIGH)
    out = main(["--run", f"base={base}", "--run", f"ast={better}", "--out", str(tmp_path / "comparison.md")])
    text = out.read_text()

    assert "Reference (first column): **base**" in text
    assert "| base | splitter, header off | 85 |" in text and "| ast | ast, header off | 60 |" in text      # what each run was
    assert "Retrieval configuration: `hybrid+rerank`" in text and "RAGAS (LLM judge, 0 to 1)" in text
    assert "| Hit@5 (all needed passages found) | 0.50 | 1.00 (+0.50 better) |" in text
    assert "| Faithfulness (no hallucination) | 0.50 | 0.90 (+0.40 better) |" in text
    assert "ast vs base, `hybrid+rerank`: 1 question(s)" in text
    assert "c13 (global)" in text and "retrieval hit 0 -> 1" in text and "answer correct 0 -> 1" in text
    assert "c01" not in text.split("ast vs base")[1]                       # c01 did not change, so it is not listed


def test_a_drop_in_a_lower_is_better_metric_is_called_better_and_a_rise_in_a_higher_is_better_one_worse():
    from eval_code.compare import _cell

    assert _cell(0.10, 0.30, "false_abstention", 2, False) == "0.10 (-0.20 better)"       # fewer false refusals
    assert _cell(0.60, 0.80, "hit@5", 2, False) == "0.60 (-0.20 worse)"
    assert _cell(0.80, 0.80, "hit@5", 2, False) == "0.80 (=)"
    assert _cell(0.80, 0.30, "hit@5", 2, True) == "0.80"                                    # the reference column has no delta
    assert _cell(None, 0.30, "hit@5", 2, False) == "-"


def test_the_comparison_works_without_ragas_and_with_three_runs(tmp_path):
    from eval_code.compare import main

    runs = [_fake_run(tmp_path, n, (1, 0), (1, 0)) for n in ("a", "b", "c")]
    text = main(["--run", f"a={runs[0]}", "--run", f"b={runs[1]}", "--run", f"c={runs[2]}", "--out", str(tmp_path / "c.md")]).read_text()
    assert "RAGAS (LLM judge" not in text and "b vs a" in text and "c vs a" in text and ": 0 question(s)" in text


@pytest.mark.parametrize("args", [["--run", "only=x"], ["--run", "noequals", "--run", "b=y"]])
def test_the_comparison_refuses_bad_arguments(args, tmp_path):
    from eval_code.compare import main

    with pytest.raises((SystemExit, FileNotFoundError)):
        main([*args, "--out", str(tmp_path / "x.md")])


def test_the_comparison_refuses_two_runs_with_the_same_name(tmp_path):
    from eval_code.compare import main

    run = _fake_run(tmp_path, "same", (1, 0), (1, 0))
    with pytest.raises(SystemExit):
        main(["--run", f"x={run}", "--run", f"x={run}", "--out", str(tmp_path / "x.md")])


def test_a_folder_that_is_not_a_run_is_reported(tmp_path):
    from eval_code.compare import load_run

    with pytest.raises(FileNotFoundError):
        load_run("empty", tmp_path)


# --- 5. fairness: can every question be answered in principle? --------------------------------------------------------------


@pytest.fixture(scope="module")
def chunked_corpus():
    """Every corpus file through the REAL ingestion pipeline (loader, chunker), with the embedder replaced by a recorder."""
    from app.ingestion import pipeline

    captured: dict[str, list[Document]] = {}

    class Recorder:
        def __init__(self):
            self.current = None

        def embed_and_index(self, chunks):
            captured[self.current] = list(chunks)
            return [str(i) for i in range(len(chunks))]

    recorder = Recorder()
    original = pipeline.get_embedding_orchestrator
    pipeline.get_embedding_orchestrator = lambda: recorder
    try:
        for source in build_corpus():
            recorder.current = source.filename
            result = pipeline.ingest_file(source.data, source.filename, source.mime, {"document_id": "1", "source_name": source.filename})
            assert result.success, (source.filename, result.error)
    finally:
        pipeline.get_embedding_orchestrator = original
    return captured


def test_every_file_is_split_into_several_chunks_so_retrieval_has_real_work(chunked_corpus):
    total = sum(len(chunks) for chunks in chunked_corpus.values())
    assert len(chunked_corpus) == 24 and total >= 40            # the Stage 2 splitter makes 85 of them, the AST chunker fewer
    assert sum(1 for chunks in chunked_corpus.values() if len(chunks) >= 2) >= 10


def test_every_expected_passage_lies_whole_inside_one_chunk(chunked_corpus):
    """Otherwise the question measures where the chunker cut, not retrieval, and no retriever could ever hit it."""
    unfair = []
    for g in ALL:
        for e in g["expected"]:
            if not any(is_relevant({"source": e["doc"], "text": c.page_content}, e) for c in chunked_corpus[e["doc"]]):
                unfair.append((g["id"], e["doc"], e["passage"][:60]))
    assert not unfair, f"passages cut by the chunker: {unfair}"


def test_the_chunk_holding_each_passage_reports_line_numbers_that_cover_it(chunked_corpus):
    """Stage 3's line numbers, checked on real code: a citation of that chunk must point at the passage's real lines."""
    wrong = []
    for g in ALL:
        for e in g["expected"]:
            holders = [c for c in chunked_corpus[e["doc"]] if is_relevant({"source": e["doc"], "text": c.page_content}, e)]
            first, last = e["lines"]
            if not any(c.metadata.get("start_line", 10**9) <= first and c.metadata.get("end_line", 0) >= last for c in holders):
                wrong.append((g["id"], e["doc"], first, last, [(c.metadata.get("start_line"), c.metadata.get("end_line")) for c in holders]))
    assert not wrong, wrong


# --- 6. command line -------------------------------------------------------------------------------------------------------


def test_cli_defaults_and_options():
    from eval_code.run import parse_args

    args = parse_args([])
    assert args.split == "dev" and args.tag is None and args.code_chunker is None and args.code_header is None
    assert args.configs == CONFIG_NAMES and not args.no_ragas and args.generator == "ollama" and args.judge == "ollama"
    custom = parse_args(["--split", "test", "--tag", "x", "--code-chunker", "splitter", "--code-header", "on"])
    assert (custom.split, custom.tag, custom.code_chunker, custom.code_header) == ("test", "x", "splitter", "on")
    for bad in (["--split", "validation"], ["--code-chunker", "magic"], ["--code-header", "maybe"], ["--suite", "code"]):
        with pytest.raises(SystemExit):
            parse_args(bad)


def test_the_runner_uses_its_own_collection_and_applies_the_experiment_flags(monkeypatch):
    from eval_code.run import COLLECTION, configure_environment, parse_args

    assert COLLECTION == "knowledgeos_eval_code"
    monkeypatch.delenv("QDRANT_COLLECTION", raising=False)
    monkeypatch.setenv("CODE_CHUNKER", "ast")                                      # (restored after the test)
    monkeypatch.setenv("CODE_CHUNK_HEADER", "false")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    configure_environment(parse_args(["--code-chunker", "splitter", "--code-header", "on"]))
    assert os.environ["QDRANT_COLLECTION"] == "knowledgeos_eval_code"
    assert os.environ["CODE_CHUNKER"] == "splitter" and os.environ["CODE_CHUNK_HEADER"] == "true"
    assert os.environ["LANGSMITH_TRACING"] == "false"
    monkeypatch.delenv("QDRANT_COLLECTION")                                         # setdefault wrote it: clean up for other tests


def test_the_runner_defaults_to_the_dev_split_and_never_picks_the_sealed_split_by_accident():
    from eval_code.run import choose_golden, parse_args

    assert {g["split"] for g in choose_golden(parse_args([]))} == {"dev"}
    assert {g["split"] for g in choose_golden(parse_args(["--split", "test"]))} == {"test"}
    assert len(choose_golden(parse_args(["--split", "all"]))) == 25
    assert len(choose_golden(parse_args(["--limit", "3"]))) == 3
    assert {g["type"] for g in choose_golden(parse_args(["--types", "global"]))} == {"global"}


@pytest.mark.parametrize("collection", ["documents", "knowledgeos_eval"])
def test_the_code_evaluation_refuses_the_production_and_the_documents_evaluation_collections(collection):
    result = run_python("from eval_code.ingest import ingest_corpus\ningest_corpus()", QDRANT_COLLECTION=collection)
    assert result.returncode != 0 and "refusing" in result.stderr


def test_the_ragas_questions_are_chosen_hard_first():
    from eval_code.run import choose_ragas_questions

    dev = load_golden_set("dev")
    everything = choose_ragas_questions(dev, None)
    assert everything == {g["id"] for g in dev if g["answerable"]} and len(everything) == 14
    few = choose_ragas_questions(dev, 6)
    assert len(few) == 6 and all(g["type"] != "direct" for g in dev if g["id"] in few)


# --- 7. the real pipeline on the code corpus (Qdrant + models) ----------------------------------------------------------------


@pytest.fixture(scope="module")
def ingested_code():
    from app.ingestion.embedding.models import EmbeddingConfig
    from app.ingestion.embedding.vector_store import get_qdrant_client
    from app.ingestion.pipeline import get_embedding_orchestrator
    from app.retrieval.orchestrator import get_search_store
    from eval_code.ingest import ingest_corpus

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


def test_the_code_corpus_ingests_into_many_chunks(ingested_code):
    assert ingested_code["documents"] == 24 and ingested_code["chunks"] >= 40


@pytest.mark.parametrize("config", CONFIG_NAMES)
def test_every_configuration_produces_a_complete_code_sample(ingested_code, config):
    from langchain_core.runnables import RunnableLambda

    from eval_code.pipelines import run_question

    # A fake that always answers: the shared test fake picks its reply by looking for phrases in the prompt
    # ("different phrasings", "Standalone query"), and this corpus CONTAINS those phrases (retrieval/multi_query.py).
    always = RunnableLambda(lambda prompt_value: "It is a token bucket limiter [1].")
    gold = next(g for g in ALL if g["id"] == "c01")
    sample = run_question(config, gold, always)
    assert sample["config"] == config and sample["contexts"] and sample["answer"]
    first = sample["contexts"][0]
    assert first["source"].startswith(("backend/", "frontend/")) and isinstance(first["start_line"], int) and isinstance(first["end_line"], int)
    assert sample["cited"] and all(c["file_path"] and isinstance(c["start_line"], int) for c in sample["cited"])


@pytest.mark.parametrize("config", ["hybrid", "hybrid+rerank"])
def test_the_keyword_and_hybrid_configurations_find_an_easy_identifier_question(ingested_code, config):
    from eval_code.metrics import retrieval_metrics
    from eval_code.pipelines import describe, retrieve_chunks

    gold = next(g for g in ALL if g["id"] == "c01")
    assert retrieval_metrics(describe(retrieve_chunks(config, gold["question"])), gold["expected"])["hit"] == 1.0


@needs_ollama
def test_the_runner_end_to_end_writes_a_report_and_metadata(ingested_code, tmp_path):
    from eval_code.run import main

    out_dir = main(["--limit", "3", "--configs", "hybrid", "--no-ragas", "--skip-ingest", "--reuse", str(tmp_path)])
    report = (out_dir / "report.md").read_text()
    assert "# Code RAG evaluation report" in report and "Cites the expected file AND its lines" in report and "split: dev" in report
    samples = json.loads((out_dir / "samples_hybrid.json").read_text())
    assert len(samples) == 3 and all(s["id"].startswith("c") for s in samples)
    meta = json.loads((out_dir / "meta.json").read_text())
    assert meta["split"] == "dev" and meta["configs"] == ["hybrid"] and "chunking" in meta
