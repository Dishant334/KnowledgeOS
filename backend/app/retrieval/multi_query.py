# app/retrieval/multi_query.py

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.language_models import BaseChatModel

_MULTI_QUERY_PROMPT = ChatPromptTemplate.from_template(
    """Generate {num_variants} different phrasings of the following search
query, so that different wordings might surface different relevant
documents. Return ONLY the variants, one per line, no numbering.

Query: {query}"""
)


def build_multi_query_chain(llm: BaseChatModel):
    """
    Returns an LCEL chain: {query, num_variants} -> raw LLM text output
    (newline-separated variants). 
    """
    return _MULTI_QUERY_PROMPT | llm | StrOutputParser()


def generate_query_variants(chain, query: str, num_variants: int) -> list[str]:
    raw_output = chain.invoke({"query": query, "num_variants": num_variants})
    variants = [line.strip() for line in raw_output.split("\n") if line.strip()]
    # always include the original rewritten query itself as one variant
    return [query] + variants[:num_variants]


