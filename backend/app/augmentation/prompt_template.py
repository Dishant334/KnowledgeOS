# app/augmentation/prompt_templates.py

from langchain_core.prompts import ChatPromptTemplate

GENERATION_PROMPT = ChatPromptTemplate.from_template(
    """Answer the user's question using ONLY the context below.
Cite sources inline using the bracketed numbers, e.g. [1], [2].
If the context does not contain enough information to answer,
say "I don't have enough information to answer that" — do not guess.

Context:
{context}

Question: {question}

Answer:"""
)