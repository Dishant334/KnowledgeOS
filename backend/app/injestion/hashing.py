# app/ingestion/hashing.py
import hashlib

def compute_document_hash(file_bytes: bytes) -> str:
    return hashlib.sha256(file_bytes).hexdigest()