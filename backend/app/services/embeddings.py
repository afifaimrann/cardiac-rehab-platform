"""Pluggable text encoders.

Which encoder runs is a deployment decision, not an architectural one, so the
rest of the system depends on the `Embedder` protocol and never on a specific
library. Selection is by configuration with an availability check, so a missing
optional dependency degrades the system to lexical retrieval instead of
crashing it at import time.

Options, in the order `get_embedder()` tries them:

  fastembed          ONNX, no torch, ~100 MB installed. Good default.
  sentence-transformers  torch, ~2 GB installed. Use if it is already present.
  openai             No local install, needs a key and a network round trip.
  hash               Deterministic, dependency-free, NOT semantic. Tests only.
"""
from __future__ import annotations

import hashlib
import logging
import math
from typing import List, Optional, Protocol, Sequence

from app.core.config import settings

logger = logging.getLogger("cardiac.embeddings")


class Embedder(Protocol):
    name: str
    dim: int

    def encode(self, texts: Sequence[str]) -> List[List[float]]: ...

    def encode_query(self, text: str) -> List[float]: ...


def _normalise(vector: Sequence[float]) -> List[float]:
    """Unit-length vectors, so cosine similarity is a plain dot product and the
    database can use the cheaper inner-product path."""
    norm = math.sqrt(sum(v * v for v in vector))
    return [v / norm for v in vector] if norm else list(vector)


# E5-family models are trained with asymmetric prefixes and lose noticeable
# retrieval quality without them: the query and the passage must be marked as
# what they are. Models outside the family -- BGE-M3 included, which is trained
# without instruction prefixes -- take none, and adding one would hurt.
QUERY_PREFIXES = {"e5": "query: "}
PASSAGE_PREFIXES = {"e5": "passage: "}


def _prefix_family(model_name: str) -> Optional[str]:
    return "e5" if "e5" in model_name.lower() else None


class FastEmbedEmbedder:
    """ONNX-backed sentence embeddings; no torch."""

    def __init__(self, model_name: Optional[str] = None) -> None:
        from fastembed import TextEmbedding

        model_name = model_name or settings.EMBEDDING_MODEL
        self._model = TextEmbedding(model_name=model_name)
        self.name = f"fastembed:{model_name}"
        self.dim = settings.EMBEDDING_DIM
        self._family = _prefix_family(model_name)

    def _embed(self, texts: Sequence[str]) -> List[List[float]]:
        return [_normalise(v.tolist()) for v in self._model.embed(list(texts))]

    def encode(self, texts: Sequence[str]) -> List[List[float]]:
        """Encode passages for storage."""
        prefix = PASSAGE_PREFIXES.get(self._family or "", "")
        return self._embed([f"{prefix}{t}" for t in texts])

    def encode_query(self, text: str) -> List[float]:
        prefix = QUERY_PREFIXES.get(self._family or "", "")
        return self._embed([f"{prefix}{text}"])[0]


class FlagEmbeddingEncoder:
    """BGE-M3 through BAAI's own loader.

    Preferred for this checkpoint: FlagEmbedding is what the model was released
    with, so the pooling and normalisation match how it was trained, and it pins
    a transformers version it is tested against. It also pairs with FlagReranker
    without the two libraries disagreeing about which transformers to use.
    """

    def __init__(self, model_name: Optional[str] = None) -> None:
        from FlagEmbedding import BGEM3FlagModel

        model_name = model_name or settings.EMBEDDING_MODEL
        self._model = BGEM3FlagModel(model_name, use_fp16=False)
        self.name = f"flagembedding:{model_name}"
        self.dim = settings.EMBEDDING_DIM

    def _embed(self, texts: Sequence[str]) -> List[List[float]]:
        output = self._model.encode(
            list(texts), batch_size=8, max_length=1024, return_dense=True,
            return_sparse=False, return_colbert_vecs=False,
        )
        # BGE-M3 dense vectors come out normalised; normalise anyway so the
        # dot-product assumption downstream holds regardless of library version.
        return [_normalise(vector.tolist()) for vector in output["dense_vecs"]]

    def encode(self, texts: Sequence[str]) -> List[List[float]]:
        return self._embed(texts)

    def encode_query(self, text: str) -> List[float]:
        # BGE-M3 is symmetric: no query prefix, unlike the E5 family.
        return self._embed([text])[0]


class SentenceTransformerEmbedder:
    def __init__(self, model_name: Optional[str] = None) -> None:
        from sentence_transformers import SentenceTransformer

        model_name = model_name or settings.EMBEDDING_MODEL
        self._model = SentenceTransformer(model_name)
        self.name = f"sentence-transformers:{model_name}"
        # The accessor was renamed in sentence-transformers 3.x; support both so
        # the code works across the versions people actually have installed.
        getter = getattr(self._model, "get_embedding_dimension", None) or \
            self._model.get_sentence_embedding_dimension
        self.dim = int(getter())

    def encode(self, texts: Sequence[str]) -> List[List[float]]:
        prefix = PASSAGE_PREFIXES.get(_prefix_family(self.name) or "", "")
        vectors = self._model.encode(
            [f"{prefix}{t}" for t in texts], normalize_embeddings=True
        )
        return [list(map(float, v)) for v in vectors]

    def encode_query(self, text: str) -> List[float]:
        prefix = QUERY_PREFIXES.get(_prefix_family(self.name) or "", "")
        vector = self._model.encode([f"{prefix}{text}"], normalize_embeddings=True)[0]
        return list(map(float, vector))


class OpenAIEmbedder:
    def __init__(self, model_name: str = "text-embedding-3-small") -> None:
        from openai import OpenAI

        self._client = OpenAI(api_key=settings.OPENAI_API_KEY, timeout=30.0)
        self._model_name = model_name
        self.name = f"openai:{model_name}"
        self.dim = 1536

    def encode(self, texts: Sequence[str]) -> List[List[float]]:
        # Batched: one request per chunk would be slow and needlessly expensive.
        response = self._client.embeddings.create(model=self._model_name, input=list(texts))
        return [_normalise(item.embedding) for item in response.data]

    def encode_query(self, text: str) -> List[float]:
        return self.encode([text])[0]


class HashEmbedder:
    """Deterministic hashed bag-of-words. NOT semantic — for tests only.

    It exists so the storage, fusion and API layers can be tested end to end
    without downloading a model. It will happily match on shared tokens and
    understands nothing; never configure it in a real deployment.
    """

    def __init__(self, dim: int = 256) -> None:
        self.name = "hash:test-only"
        self.dim = dim

    def encode(self, texts: Sequence[str]) -> List[List[float]]:
        from app.services.retrieval import tokenize

        vectors: List[List[float]] = []
        for text in texts:
            vector = [0.0] * self.dim
            for token in tokenize(text):
                digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
                index = int.from_bytes(digest[:4], "big") % self.dim
                sign = 1.0 if digest[4] % 2 == 0 else -1.0
                vector[index] += sign
            vectors.append(_normalise(vector))
        return vectors

    def encode_query(self, text: str) -> List[float]:
        return self.encode([text])[0]


_BACKENDS = {
    "flagembedding": FlagEmbeddingEncoder,
    "fastembed": FastEmbedEmbedder,
    "sentence-transformers": SentenceTransformerEmbedder,
    "openai": OpenAIEmbedder,
    "hash": HashEmbedder,
}

_cached: Optional[Embedder] = None


def get_embedder(force: Optional[str] = None) -> Optional[Embedder]:
    """The configured encoder, or None when none is available.

    None is a supported state: retrieval falls back to BM25 alone, which is why
    the system still answers with no ML dependency installed.
    """
    global _cached
    if _cached is not None and force is None:
        return _cached

    preference = force or settings.EMBEDDING_BACKEND
    order = [preference] if preference != "auto" else [
        "flagembedding", "fastembed", "sentence-transformers", "openai",
    ]

    for name in order:
        factory = _BACKENDS.get(name)
        if factory is None:
            logger.warning("Unknown embedding backend %r", name)
            continue
        if name == "openai" and not settings.OPENAI_API_KEY:
            continue
        try:
            embedder = factory()
        except ImportError:
            logger.info("Embedding backend %r is not installed", name)
            continue
        except Exception as exc:  # noqa: BLE001
            logger.warning("Embedding backend %r failed to start: %s", name, exc)
            continue

        logger.info("Using embedding backend %s (dim=%d)", embedder.name, embedder.dim)
        if force is None:
            _cached = embedder
        return embedder

    logger.info("No embedding backend available; retrieval will be lexical only")
    return None


def reset_embedder_cache() -> None:
    global _cached
    _cached = None
