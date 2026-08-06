"""
Vector Store using ChromaDB.

Responsible for:
- Creating / loading the vector database.
- Storing embeddings + documents + metadata.
- Similarity search.
- Metadata filtering.
"""

from __future__ import annotations
import chromadb

from rag import config as cfg
from rag.chunking import Chunk


class VectorStore:
    def __init__(self):
        """Create or load the persistent Chroma database."""

        self.client = chromadb.PersistentClient(
            path=str(cfg.CHROMA_DB_DIR)
        )

        self.collection = self.client.get_or_create_collection(
            name=cfg.COLLECTION_NAME,
            metadata={
                "description": "Torque Tune Knowledge Base"
            }
        )

    # ----------------------------------------------------
    # Insert
    # ----------------------------------------------------

    def add_chunks(
        self,
        chunks: list[Chunk],
        embeddings,
    ) -> None:
        """
        Store chunks inside ChromaDB.

        Parameters
        ----------
        chunks:
            List of Chunk objects.

        embeddings:
            numpy array returned by the embedder.
            Shape:
                (number_of_chunks, embedding_dimension)
        """

        if len(chunks) != len(embeddings):
            raise ValueError(
                "Number of chunks and embeddings must match."
            )

        ids = []
        documents = []
        metadatas = []
        vectors = []

        for chunk, vector in zip(chunks, embeddings):

            ids.append(
                f"{chunk.doc_id}_{chunk.chunk_index}"
            )

            documents.append(chunk.text)

            metadatas.append(chunk.metadata)

            vectors.append(vector.tolist())

        self.collection.add(
            ids=ids,
            documents=documents,
            embeddings=vectors,
            metadatas=metadatas,
        )

    # ----------------------------------------------------
    # Search
    # ----------------------------------------------------

    def search(
        self,
        query_embedding,
        top_k: int = 5,
    ):
        """
        Standard vector similarity search.
        """

        return self.collection.query(
            query_embeddings=[query_embedding.tolist()],
            n_results=top_k,
        )

    # ----------------------------------------------------
    # Search + Metadata Filter
    # ----------------------------------------------------

    def search_with_filter(
        self,
        query_embedding,
        metadata_filter: dict,
        top_k: int = 5,
    ):
        """
        Similarity search with metadata filtering.
        """

        return self.collection.query(
            query_embeddings=[query_embedding.tolist()],
            n_results=top_k,
            where=metadata_filter,
        )

    # ----------------------------------------------------
    # Collection Utilities
    # ----------------------------------------------------

    def count(self) -> int:
        """
        Number of stored chunks.
        """
        return self.collection.count()

    def peek(self, limit: int = 5):
        """
        Inspect stored chunks.
        """

        return self.collection.peek(limit)

    def reset(self):
        try:
            self.client.delete_collection(cfg.COLLECTION_NAME)
        except Exception:
            pass

        self.collection = self.client.get_or_create_collection(
            name=cfg.COLLECTION_NAME
    )