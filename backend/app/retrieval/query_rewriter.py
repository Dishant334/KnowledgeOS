# app/retrieval/query_rewriter.py

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.language_models import BaseChatModel

_REWRITE_PROMPT = ChatPromptTemplate.from_template(
    """Rewrite the user's question into a standalone search query.
Resolve any pronouns or references using the conversation history.
Return ONLY the rewritten query, nothing else.

Conversation history:
{history}

User question: {question}

Standalone query:"""
)


def build_query_rewriter(llm: BaseChatModel):
    """
    Returns an LCEL chain: {question, history} -> standalone query string.
    """
    return _REWRITE_PROMPT | llm | StrOutputParser()