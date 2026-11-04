# eval/compat.py
"""
RAGAS 0.4.3 (the latest release) imports two Google Vertex AI classes from langchain-community
that langchain-community 0.4.2 (the latest stable release) no longer contains, so
`import ragas` crashes. RAGAS only uses them in an isinstance() check ("does this model support
n completions?"). We never use Vertex, so harmless stand-in classes are enough.

Call install_ragas_compat() BEFORE importing ragas. Remove this file when RAGAS fixes the import.
"""

import sys
import types


class _NotUsed:
    """Stand-in for a class we never use; nothing is ever an instance of it."""


def install_ragas_compat() -> None:
    try:
        from langchain_community.chat_models.vertexai import ChatVertexAI  # noqa: F401
    except ImportError:
        module = types.ModuleType("langchain_community.chat_models.vertexai")
        module.ChatVertexAI = _NotUsed
        sys.modules["langchain_community.chat_models.vertexai"] = module

    import langchain_community.llms as llms

    try:
        llms.VertexAI
    except (ImportError, AttributeError):
        llms.VertexAI = _NotUsed
