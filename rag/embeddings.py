from __future__ import annotations
import pickle
from abc import ABC, abstractmethod
from pathlib import Path
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.decomposition import TruncatedSVD
from sklearn.preprocessing import normalize

from rag import config as cfg

from dotenv import load_dotenv

load_dotenv()


class Embedder(ABC):
    dim: int

    @abstractmethod
    def fit(self, texts: list[str]) -> None: ...

    @abstractmethod
    def embed(self, texts: list[str]) -> np.ndarray: ...

    def embed_one(self, text: str) -> np.ndarray:
        return self.embed([text])[0]

# ممكن اشيل ده لو مش  محتاجاه 
class LocalLSAEmbedder(Embedder):
    """Offline embedder: TF-IDF (word 1-2 grams) -> TruncatedSVD -> L2-normalize."""

    def __init__(self, dim: int = cfg.EMBEDDING_DIM):
        self.dim = dim
        self.vectorizer = TfidfVectorizer(
            max_features=20000, ngram_range=(1, 2), sublinear_tf=True,
            min_df=1, max_df=0.9,
        )
        self.svd = TruncatedSVD(n_components=dim, random_state=cfg.RANDOM_SEED)
        self._fitted = False

    def fit(self, texts: list[str]) -> None:
        tfidf = self.vectorizer.fit_transform(texts)
        eff_dim = min(self.dim, tfidf.shape[1] - 1, tfidf.shape[0] - 1)
        if eff_dim != self.dim:
            self.svd = TruncatedSVD(n_components=eff_dim, random_state=cfg.RANDOM_SEED)
            self.dim = eff_dim
        self.svd.fit(tfidf)
        self._fitted = True

    def embed(self, texts: list[str]) -> np.ndarray:
        if not self._fitted:
            raise RuntimeError("LocalLSAEmbedder.fit() must be called before embed().")
        tfidf = self.vectorizer.transform(texts)
        vecs = self.svd.transform(tfidf)
        return normalize(vecs).astype("float32")

    def save(self, path: Path) -> None:
        with open(path, "wb") as f:
            pickle.dump({"vectorizer": self.vectorizer, "svd": self.svd, "dim": self.dim}, f)

    def load(self, path: Path) -> None:
        with open(path, "rb") as f:
            state = pickle.load(f)
        self.vectorizer = state["vectorizer"]
        self.svd = state["svd"]
        self.dim = state["dim"]
        self._fitted = True


class GeminiEmbedder(Embedder):
    """Production embedder via google-genai. Not exercised in this sandbox
    (no network route / no API key here) -- wired to match this project's
    existing stack so it's a config flip, not new plumbing, in a real deploy.
    """

    def __init__(self, model: str = cfg.GEMINI_EMBEDDING_MODEL, api_key: str | None = None):
        import os
        self.model = model
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY not set; required for GeminiEmbedder.")
        from google import genai  # matches google-genai in requirements.txt
        self._client = genai.Client(api_key=self.api_key)
        self.dim = 3072  # gemini-embedding-001 default; truncate/MRL as needed

    def fit(self, texts: list[str]) -> None:
        return  # no local fitting needed for an API-backed embedder

    def embed(self, texts: list[str]) -> np.ndarray:
        vecs = []
        for t in texts:
            resp = self._client.models.embed_content(model=self.model, contents=t)
            vecs.append(resp.embeddings[0].values)
        return normalize(np.array(vecs, dtype="float32"))


def get_embedder() -> Embedder:
    if cfg.EMBEDDING_PROVIDER == "gemini":
        return GeminiEmbedder()
    return LocalLSAEmbedder()
