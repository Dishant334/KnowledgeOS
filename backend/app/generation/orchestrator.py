# app/generation/orchestrator.py

from app.retrieval.orchestrator import retrieve
from app.augmentation.context_builder import ContextBuilder
from app.generation.chain import build_generation_chain
from app.generation.memory import wrap_with_history
from app.generation.models import GenerationResult

context_builder = ContextBuilder()


def ask(question: str, llm, session_id: str, **retrieval_kwargs) -> GenerationResult:
    """
    Full ask flow: retrieve -> augment -> generate, with ONE shared
    Postgres-backed history (via session_id) used by both retrieval's
    query rewriting AND generation's conversational memory.
    """
    retrieval_result = retrieve(question, llm=llm, session_id=session_id, **retrieval_kwargs)

    augmented = context_builder.build(retrieval_result.chunks)

    chain = build_generation_chain(llm)
    chain_with_history = wrap_with_history(chain)

    answer = chain_with_history.invoke(
        {"context": augmented.prompt_context, "question": question},
        config={"configurable": {"session_id": session_id}},
    )

    abstained = "don't have enough information" in answer.lower()

    return GenerationResult(
        answer=answer,
        citations=augmented.citations,
        abstained=abstained,
    )