"""
Ingest the knowledge corpus into ChromaDB (non-destructive by default).

Run:
    python -m rag.ingest
"""
from __future__ import annotations

from rag import config as cfg
from rag.chunking import build_all_chunks
from rag.embeddings import get_embedder
from rag.vector_store import VectorStore


def ingest(reset_db: bool = False) -> VectorStore:
    print("=" * 60)
    print("Building chunks...")
    chunks = build_all_chunks()
    print(f"Created {len(chunks)} chunks.")

    print("\nLoading embedding model...")
    embedder = get_embedder()
    texts = [chunk.text for chunk in chunks]
    if cfg.EMBEDDING_PROVIDER.lower() == "local":
        print("Training Local LSA embedding model...")
        embedder.fit(texts)
    print("Generating embeddings...")
    embeddings = embedder.embed(texts)
    print(f"Embedding dimension: {embedder.dim}")

    print("\nConnecting to ChromaDB...")
    store = VectorStore()

    if reset_db:
        print("Resetting collection (full rebuild)...")
        store.reset()
    else:
        # Non-destructive refresh:
        # 1) wipe only the docs that exist on disk (re-added below)
        # 2) prune docs that were removed from disk
        on_disk = {c.doc_id for c in chunks}
        for doc_id in sorted(on_disk):
            store.delete_by_doc(doc_id)
        for missing in sorted(store.known_doc_ids() - on_disk):
            print(f"Pruning removed document: {missing}")
            store.delete_by_doc(missing)

    print("Storing vectors...")
    store.add_chunks(chunks=chunks, embeddings=embeddings)

    print("\nIngestion completed successfully.")
    print(f"Stored chunks: {store.count()}")
    return store


if __name__ == "__main__":
    # Non-destructive: never drop the collection while the platform is live.
    ingest(reset_db=False)