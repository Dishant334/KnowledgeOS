# app/ingestion/cleaning/base.py

from abc import ABC, abstractmethod
from typing import Optional

from langchain_core.documents import Document


class DocumentCleaner(ABC):
    """
    Interface every cleaning step implements.

    clean() returns the cleaned Document, or None to signal that this
    document should be dropped from the pipeline entirely (e.g. it
    failed a hard quality floor). Returning None short-circuits any
    remaining cleaners for that document — see CleaningPipeline.run().
    """

    @abstractmethod
    def clean(self, document: Document) -> Optional[Document]:
        raise NotImplementedError