# app/core/storage.py
from abc import ABC, abstractmethod


class StorageBackend(ABC):
    @abstractmethod
    async def save(self, path: str, data: bytes) -> None: ...
    @abstractmethod
    async def read(self, path: str) -> bytes: ...
    @abstractmethod
    async def delete(self, path: str) -> None: ...