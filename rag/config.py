from pathlib import Path

BASE_DIR = Path(__file__).parent


# Corpus
DOCUMENTS_DIR = BASE_DIR / "documents"
RAG_DB_PATH = BASE_DIR.parent / "db" / "redline.db"


# ChromaDB
CHROMA_DB_DIR = BASE_DIR / "chroma_db"
COLLECTION_NAME = "torque_tune"

# Embeddings
EMBEDDING_PROVIDER = "gemini"     # "gemini" أو "local"
GEMINI_EMBEDDING_MODEL = "gemini-embedding-001"
EMBEDDING_DIM = 384
RANDOM_SEED = 42

# Retrieval
TOP_K = 5

# Chunking
CHUNK_TARGET_TOKENS = 300
CHUNK_OVERLAP_TOKENS = 50

GENERATOR_MODEL_NAME = "gemini-flash-latest"
TEMPERATURE = 0

RRF_K = 60
HYBRID_CANDIDATE_MULTIPLIER = 2