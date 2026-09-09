# app/generation/chain.py

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser

GENERATION_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """Answer the user's question using ONLY the context below.
Cite sources inline using the bracketed numbers, e.g. [1], [2].
If the context does not contain enough information to answer,
say "I don't have enough information to answer that" — do not guess.

Context:
{context}"""),
    MessagesPlaceholder(variable_name="history"),
    ("human", "{question}"),
])


def build_generation_chain(llm):
    """
    LCEL chain: {context, question, history} -> answer string.
    `history` is populated automatically by RunnableWithMessageHistory
    (see memory.py) — callers invoking this chain directly (without
    the history wrapper) should pass history=[] explicitly.
    """
    return GENERATION_PROMPT | llm | StrOutputParser()