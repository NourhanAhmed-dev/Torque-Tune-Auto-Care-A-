# to creat chrom db (vectos store) from the knowledge corpus
"""
Ingest the knowledge corpus into ChromaDB.

Pipeline

Documents
    ↓
Chunking
    ↓
Embeddings
    ↓
Vector Store
    ↓
ChromaDB

Run:
    python -m rag.ingest
"""

from __future__ import annotations

from rag import config as cfg
from rag.chunking import build_all_chunks
from rag.embeddings import get_embedder
from rag.vector_store import VectorStore


def ingest(reset_db: bool = False) -> VectorStore:
    """
    Build the vector database.

    Parameters
    ----------
    reset_db : bool
        If True, delete the existing Chroma collection
        before inserting the new data.
    """

    print("=" * 60)
    print("Building chunks...")
    print("=" * 60)

    chunks = build_all_chunks()

    print(f"Created {len(chunks)} chunks.")

    print("\nLoading embedding model...")

    embedder = get_embedder()

    texts = [chunk.text for chunk in chunks]

    # Local LSA يحتاج تدريب، أما Gemini فلا.
    if cfg.EMBEDDING_PROVIDER.lower() == "local":
        print("Training Local LSA embedding model...")
        embedder.fit(texts)

    print("Generating embeddings...")

    embeddings = embedder.embed(texts)

    print(f"Embedding dimension: {embedder.dim}")

    print("\nConnecting to ChromaDB...")

    store = VectorStore()

    if reset_db:
        print("Resetting collection...")
        store.reset()

    print("Storing vectors...")

    store.add_chunks(
        chunks=chunks,
        embeddings=embeddings,
    )

    print("\nIngestion completed successfully.")
    print(f"Stored chunks: {store.count()}")

    print("\nSample stored documents:")

    sample = store.peek(3)

    if sample:
        print(sample)

    return store


if __name__ == "__main__":
    # أثناء التطوير اجعليها True
    # وبعدها خليها False في التشغيل العادي
    ingest(reset_db=False)