"""
Observability: LangSmith tracing.

  1. Configuration   .env values must reach the process environment (they used to be ignored)
  2. Trace content   what appears in the trace tree, and what is deliberately left out
                     (uses a RECORDING FAKE client: nothing is uploaded, no account needed)
"""

import os
import subprocess
import sys

import pytest
from langsmith import Client, tracing_context

from app.core.tracing import PREVIEW_CHARS
from app.generation.orchestrator import generate_answer
from app.retrieval.orchestrator import retrieve
from app.schemas.ask import AskRequest
from app.services.ask import ask_question
from tests.conftest import BACKEND_DIR, make_fake_llm
from tests.test_retrieve_ask_api import users  # noqa: F401  (fixture)
from tests.test_retrieval_units import chunk


# --- 1. configuration ---------------------------------------------------------------------------------------


def settings_in_fresh_process(tmp_path, env_file="", **env):
    """
    Settings are built when the module is imported, so check in a fresh interpreter.
    It runs in an EMPTY directory (so the real backend/.env is not read) with an optional throwaway .env.
    """
    (tmp_path / ".env").write_text(env_file)
    code = (
        "import os\n"
        "from app.core.config import settings, tracing_enabled\n"
        "from langsmith.utils import tracing_is_enabled\n"
        "print(tracing_enabled, tracing_is_enabled(), os.environ.get('LANGSMITH_TRACING'), os.environ.get('LANGSMITH_PROJECT'),"
        " os.environ.get('LANGSMITH_ENDPOINT'), os.environ.get('LANGSMITH_HIDE_INPUTS'), bool(os.environ.get('LANGSMITH_API_KEY')))"
    )
    base = {k: v for k, v in os.environ.items() if not k.startswith("LANGSMITH")}
    result = subprocess.run([sys.executable, "-W", "ignore", "-c", code], cwd=tmp_path, text=True, capture_output=True,
                            env={**base, "PYTHONPATH": str(BACKEND_DIR), "PYTHONDONTWRITEBYTECODE": "1", **env}, timeout=120)
    assert result.returncode == 0, result.stderr[-800:]
    return result.stdout.split()


def test_tracing_is_off_by_default(tmp_path):
    # off: only the switch is exported (as "false"); project / endpoint / hide flags are not touched
    assert settings_in_fresh_process(tmp_path) == ["False", "False", "false", "None", "None", "None", "False"]


def test_tracing_needs_both_the_switch_and_a_key(tmp_path):
    assert settings_in_fresh_process(tmp_path, LANGSMITH_TRACING="true")[:3] == ["False", "False", "false"]            # no key
    assert settings_in_fresh_process(tmp_path, LANGSMITH_API_KEY="lsv2_fake")[:3] == ["False", "False", "false"]      # key but switch off


def test_settings_from_the_env_FILE_reach_langchain(tmp_path):
    """The bug found in review: the LANGSMITH_* lines in .env were read by nobody (only a real .env file is used here)."""
    env_file = ("LANGSMITH_TRACING='True'\nLANGSMITH_API_KEY='lsv2_fake'\nLANGSMITH_PROJECT='my-project'\n"
                "LANGSMITH_ENDPOINT='https://example.test'\nLANGSMITH_HIDE_INPUTS='true'\n")
    out = settings_in_fresh_process(tmp_path, env_file=env_file)
    assert out == ["True", "True", "true", "my-project", "https://example.test", "true", "True"]


def test_the_test_suite_never_traces():
    assert os.environ["LANGSMITH_TRACING"] == "false"


# --- 2. what the trace contains -----------------------------------------------------------------------------


@pytest.fixture
def recorder():
    """A LangSmith client that records runs in memory instead of uploading them."""
    runs = {}

    class RecordingClient(Client):
        def create_run(self, **kwargs):
            runs[str(kwargs["id"])] = dict(kwargs)

        def update_run(self, run_id, **kwargs):
            # the final update repeats inputs=None: don't let it erase what create_run stored
            runs.setdefault(str(run_id), {}).update({k: v for k, v in kwargs.items() if v is not None})

    client = RecordingClient(api_key="test-key", api_url="http://127.0.0.1:1", auto_batch_tracing=False)

    class Recorder:
        def tracing(self):
            return tracing_context(enabled=True, client=client)

        def by_name(self, name):
            return [r for r in runs.values() if r.get("name") == name]

        def names(self):
            return {r.get("name") for r in runs.values()}

        def children_of(self, run):
            return [r for r in runs.values() if str(r.get("parent_run_id")) == str(run["id"])]

    return Recorder()


def test_nothing_is_recorded_when_tracing_is_off(recorder):
    generate_answer("q?", make_fake_llm(answer="Twenty days [1]."), [chunk("Twenty days.")])
    assert recorder.names() == set()


def test_generate_answer_trace_has_a_safe_summary_and_nested_llm_calls(recorder):
    llm = make_fake_llm(answer="Twenty days [1].")
    with recorder.tracing():
        generate_answer("How many days?", llm, [chunk("Twenty days."), chunk("More.")],
                        history=[("user", "hi"), ("assistant", "hello")], summary="EARLIER", memories=["Works in Berlin"])

    [root] = recorder.by_name("generate_answer")
    assert root["inputs"] == {"question": "How many days?", "num_chunks": 2, "history_messages": 2,
                              "has_summary": True, "num_memories": 1}                        # no llm object, no raw history/memory text
    assert root["outputs"] == {"answer": "Twenty days [1].", "abstained": False, "citations": ["[1]"]}
    assert recorder.children_of(root), "the LangChain prompt|llm|parser calls should nest under it"


def test_retrieval_trace_shows_the_retrieved_chunks_scores_and_stages(recorder, retrieval_corpus):
    llm = make_fake_llm(variants=["paid vacation days"])
    with recorder.tracing():
        retrieve("How many vacation days do employees get?", user_id=1, llm=llm)

    [root] = recorder.by_name("retrieve")
    assert root["inputs"] == {"question": "How many vacation days do employees get?", "doc_type": None, "document_ids": None,
                              "has_history": False, "uses_llm": True}                         # no user id, no llm object
    assert "paid vacation days" in root["outputs"]["query_variants"]
    top = root["outputs"]["chunks"][0]
    assert top["source"] == "handbook.pdf" and top["rerank_score"] is not None and top["fused_score"] is not None
    assert "twenty days of paid vacation" in top["text"] and len(top["text"]) <= PREVIEW_CHARS

    stage_names = {r["name"] for r in recorder.children_of(root)}
    assert {"hybrid_search", "rerank"} <= stage_names
    hybrid = recorder.by_name("hybrid_search")[0]
    assert hybrid["run_type"] == "retriever" and set(hybrid["inputs"]) == {"query", "k"}        # the Qdrant filter (user id) is not logged
    assert recorder.by_name("rerank")[0]["inputs"]["candidates"] >= 1


def test_ask_trace_covers_the_whole_request_without_leaking_internals(recorder, users, db):  # noqa: F811
    llm = make_fake_llm(answer="Employees get twenty days of paid vacation [1].")
    with recorder.tracing():
        response = ask_question(db, users[0].id, AskRequest(query="How many vacation days do employees get?"), llm)

    [root] = recorder.by_name("ask")
    assert root["inputs"] == {"question": "How many vacation days do employees get?", "conversation_id": None}
    assert root["outputs"]["answer"] == response.answer and root["outputs"]["citations"] == 1
    below = {r["name"] for r in recorder.children_of(root)}
    assert {"retrieve", "generate_answer"} <= below                                           # the pipeline stages hang off the request
    serialised = str(recorder.by_name("ask") + recorder.by_name("retrieve") + recorder.by_name("generate_answer"))
    assert "test-key" not in serialised and "Session" not in serialised
