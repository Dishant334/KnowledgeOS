# app/retrieval/multi_query.py

import re

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.language_models import BaseChatModel

# Why the prompt asks for new VOCABULARY, not just a reworded sentence:
# people ask in everyday words ("time off", "my boss") but documents are written in formal ones
# ("annual leave", "line manager"). Keyword search (BM25) only matches the exact words, and even
# embeddings drift when the wording differs a lot. A variant that already uses the document's
# wording finds it. The "answer-like statement" variant helps because a sentence that LOOKS like the
# passage is closer to the passage than a question is (the idea behind HyDE).
# The examples are deliberately about other topics than any test document, and the prompt gives no example SENTENCE:
# a small model copies it word for word as a variant (seen with Qwen3 8B: it pasted the example into 4 of 6 queries).
_MULTI_QUERY_PROMPT = ChatPromptTemplate.from_template(
    """Generate {num_variants} different phrasings of the following search
query, so that different wordings might surface different relevant
documents.

The documents are usually formal company texts (policies, handbooks, guides) and may use
different words than the question. So change the vocabulary, not just the word order:
- use synonyms and the formal terms such a document would use
  (for example "my boss" -> "line manager", "get my money back" -> "expense reimbursement")
- make ONE of the variants a plain statement (not a question) written the way the answer itself
  would appear in such a document, using the topic of THIS query

Return ONLY the variants, one per line, no numbering, no explanations.

Query: {query}"""
)

# "1. foo", "2) foo", "- foo", "* foo", "• foo"
_LIST_MARKER = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s*")


def build_multi_query_chain(llm: BaseChatModel):
    """
    Returns an LCEL chain: {query, num_variants} -> raw LLM text output
    (newline-separated variants).
    """
    return _MULTI_QUERY_PROMPT | llm | StrOutputParser()


def clean_variant(line: str) -> str:
    """One output line -> a plain query. Small local models add bullets, numbers and quotes despite being told not to."""
    return _LIST_MARKER.sub("", line).strip().strip("\"'“”").strip()


def generate_query_variants(chain, query: str, num_variants: int) -> list[str]:
    raw_output = chain.invoke({"query": query, "num_variants": num_variants})
    cleaned = (clean_variant(line) for line in raw_output.split("\n"))
    # drop empty lines and chatty intros such as "Here are 4 variants:"
    variants = [line for line in cleaned if line and not line.endswith(":")]
    # always include the original rewritten query itself as one variant
    return [query] + variants[:num_variants]
