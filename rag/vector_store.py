"""
Vector Store using ChromaDB.
- Create / load the persistent vector database.
- Store embeddings + documents + metadata (every chunk tagged with doc_id).
- Similarity search + metadata filtering.
- Per-document delete so admin add/remove is non-destructive.
"""
from __future__ import annotations

import chromadb

from rag import config as cfg
from rag.chunking import Chunk


class VectorStore:
    def __init__(self):
        self.client = chromadb.PersistentClient(path=str(cfg.CHROMA_DB_DIR))
        self.collection = self.client.get_or_create_collection(
            name=cfg.COLLECTION_NAME,
            metadata={
                "description": "Torque Tune Knowledge Base",
                "hnsw:space": "cosine",
            },
        )

    # Insert (upsert => safe to re-run at any time)
    def add_chunks(self, chunks: list[Chunk], embeddings) -> None:
        if len(chunks) != len(embeddings):
            raise ValueError("Number of chunks and embeddings must match.")
        ids, documents, metadatas, vectors = [], [], [], []
        for chunk, vector in zip(chunks, embeddings):
            meta = dict(chunk.metadata or {})
            meta["doc_id"] = chunk.doc_id      # tag every chunk with its source doc
            ids.append(f"{chunk.doc_id}_{chunk.chunk_index}")
            documents.append(chunk.text)
            metadatas.append(meta)
            vectors.append(vector.tolist())
        self.collection.upsert(ids=ids, documents=documents,
                               embeddings=vectors, metadatas=metadatas)

    # Search
    def search(self, query_embedding, top_k: int = 5):
        return self.collection.query(
            query_embeddings=[query_embedding.tolist()], n_results=top_k)

    def search_with_filter(self, query_embedding, metadata_filter: dict, top_k: int = 5):
        return self.collection.query(
            query_embeddings=[query_embedding.tolist()], n_results=top_k,
            where=metadata_filter)

    # Per-document management (non-destructive add/remove)
    def delete_by_doc(self, doc_id: str) -> None:
        """Delete all chunks that belong to one source document."""
        self.collection.delete(where={"doc_id": doc_id})

    def known_doc_ids(self) -> set:
        metas = self.collection.get(include=["metadatas"])["metadatas"] or []
        return {m.get("doc_id") for m in metas if m and m.get("doc_id")}

    # Utilities
    def count(self) -> int:
        return self.collection.count()

    def peek(self, limit: int = 5):
        return self.collection.peek(limit)

    def reset(self):
        try:
            self.client.delete_collection(cfg.COLLECTION_NAME)
        except Exception:
            pass
        self.collection = self.client.get_or_create_collection(
            name=cfg.COLLECTION_NAME)