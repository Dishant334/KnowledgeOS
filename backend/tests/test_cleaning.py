"""Cleaning pipeline — UNIT tests (pure Python, real cleaning stages)."""

from langchain_core.documents import Document

from app.ingestion.cleaning.orchestrator import CleaningOrchestrator

LINE = "Employees receive twenty days of paid vacation each year."


def _page(text, source="policy.pdf"):
    return Document(page_content=text, metadata={"source": source})


def test_state_does_not_leak_between_files_with_same_name():
    cleaner = CleaningOrchestrator()  # reused, like the worker's module-level instance
    for upload in range(1, 8):
        out = cleaner.process_batch([_page(f"{LINE}\nUnique text for file number {upload} here.")])
        assert LINE in out[0].page_content, f"line stripped on upload {upload}"


def test_running_header_still_stripped_within_one_document():
    header = "ACME Corp Confidential Handbook 2026"
    pages = [_page(f"{header}\nBody text for page number {i} goes here.") for i in range(1, 7)]
    out = CleaningOrchestrator().process_batch(pages)
    kept = [header in d.page_content for d in out]
    assert kept[:3] == [True, True, True]      # first min_occurrences kept
    assert not any(kept[3:])                   # repeating header stripped afterwards
    assert all("Body text for page" in d.page_content for d in out)


def test_empty_pages_dropped_and_metadata_preserved():
    out = CleaningOrchestrator().process_batch(
        [_page("   \n\n  "), Document(page_content="Real content — with “quotes”.", metadata={"source": "a", "k": 1})]
    )
    assert len(out) == 1
    assert out[0].page_content == 'Real content - with "quotes".'
    assert out[0].metadata["k"] == 1 and "quality_flags" in out[0].metadata
