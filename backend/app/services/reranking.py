"""Cross-encoder reranking of retrieved candidates.

A bi-encoder embeds the query and the passage separately and compares two
vectors that never met. A cross-encoder reads them together and scores the pair
directly. It is far too slow to run over a whole corpus and exactly right for
reordering twenty candidates.

Two things this buys, both visible in the calibration run that motivated it:

  Separation.  Bi-encoder cosines for this corpus sat in a narrow 0.28-0.70
               band, with the best irrelevant result (0.480) only 0.02 below the
               weakest relevant one (0.500). No threshold cleanly divides those.
               A cross-encoder pushes relevant pairs high and irrelevant pairs
               low, so a threshold means something.

  Cross-lingual fairness.  Bengali queries scored systematically below English
               ones for equally relevant passages, because cross-language pairs
               sit further apart in a shared embedding space. The cross-encoder
               judges relevance rather than distance, which largely removes that
               penalty -- so one threshold can serve both languages.

Optional, like the encoder: if the model is not installed, retrieval falls back
to bi-encoder order and the system keeps working.
"""
from __future__ import annotations

import logging
from typing import List, Optional, Protocol, Sequence, Tuple

from app.core.config import settings
from app.services.knowledge import Passage
from app.services.retrieval import Hit

logger = logging.getLogger("cardiac.rerank")


class Reranker(Protocol):
    name: str

    def score(self, query: str, passages: Sequence[str]) -> List[float]: ...


class FlagEmbeddingReranker:
    """bge-reranker-v2-m3 through BAAI's own loader.

    Tried first: the plain-transformers and sentence-transformers paths both
    returned scores far below the model's documented range on this stack, and
    FlagEmbedding is the loader the checkpoint was released with.
    """

    def __init__(self, model_name: Optional[str] = None) -> None:
        from FlagEmbedding import FlagReranker

        model_name = model_name or settings.RERANKER_MODEL
        self._model = FlagReranker(model_name, use_fp16=False)
        self.name = f"flagembedding:{model_name}"

    def score(self, query: str, passages: Sequence[str]) -> List[float]:
        if not passages:
            return []
        pairs = [[query, passage] for passage in passages]
        # normalize=True applies the sigmoid, so scores arrive in [0, 1] and no
        # second activation is applied here.
        raw = self._model.compute_score(pairs, normalize=True)
        values = raw if isinstance(raw, list) else [raw]
        return [float(v) for v in values]


class TransformersReranker:
    """bge-reranker-v2-m3 scored the way BAAI documents it.

    Deliberately plain transformers rather than a wrapper library.
    sentence-transformers does not recognise this checkpoint as one of its own
    ("No modules.json found ... initializing a new CrossEncoder model") and
    builds a generic head around it, which scored an exact-match pair at 0.002.
    The model is a single-logit sequence classifier; tokenise the pair, take the
    logit, apply sigmoid. Fifteen lines, no ambiguity about what ran.
    """

    def __init__(self, model_name: Optional[str] = None) -> None:
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        model_name = model_name or settings.RERANKER_MODEL
        self._torch = torch
        self._tokenizer = AutoTokenizer.from_pretrained(model_name)
        self._model = AutoModelForSequenceClassification.from_pretrained(model_name)
        self._model.eval()
        self.name = f"transformers:{model_name}"
        # 512 rather than the model's 8192: passages are ~900 characters, and a
        # shorter window is several times faster with nothing truncated.
        self._max_length = 512

    def score(self, query: str, passages: Sequence[str]) -> List[float]:
        if not passages:
            return []

        pairs = [[query, passage] for passage in passages]
        with self._torch.no_grad():
            inputs = self._tokenizer(
                pairs, padding=True, truncation=True,
                max_length=self._max_length, return_tensors="pt",
            )
            logits = self._model(**inputs, return_dict=True).logits.view(-1).float()
            return [float(v) for v in self._torch.sigmoid(logits)]


class CrossEncoderReranker:
    """sentence-transformers CrossEncoder, for checkpoints it ships support for.

    Kept as a fallback. Verify any model used through it with
    `python -m scripts.rerank_sanity` -- a wrapper built around an unrecognised
    checkpoint still returns plausible-looking numbers.
    """

    def __init__(self, model_name: Optional[str] = None) -> None:
        from sentence_transformers import CrossEncoder

        model_name = model_name or settings.RERANKER_MODEL
        self._model = CrossEncoder(model_name)
        self.name = f"cross-encoder:{model_name}"

    def score(self, query: str, passages: Sequence[str]) -> List[float]:
        import math

        pairs = [(query, passage) for passage in passages]
        raw = [float(value) for value in self._model.predict(pairs)]
        if not raw:
            return []
        # Sigmoid only if the library has not already applied one: doing it
        # twice maps [0,1] onto [0.5, 0.73] and erases the separation.
        if all(0.0 <= value <= 1.0 for value in raw):
            return raw
        return [1.0 / (1.0 + math.exp(-value)) for value in raw]


_cached: Optional[Reranker] = None
_attempted = False


def get_reranker() -> Optional[Reranker]:
    global _cached, _attempted
    if _attempted:
        return _cached
    _attempted = True

    if not settings.RERANK_ENABLED:
        logger.info("Reranking disabled by configuration")
        return None

    known = {
        "flagembedding": FlagEmbeddingReranker,
        "transformers": TransformersReranker,
        "cross-encoder": CrossEncoderReranker,
    }
    backends = (
        [FlagEmbeddingReranker, TransformersReranker, CrossEncoderReranker]
        if settings.RERANKER_BACKEND == "auto"
        else [known[settings.RERANKER_BACKEND]]
    )

    for backend in backends:
        try:
            _cached = backend()
            logger.info("Using reranker %s", _cached.name)
            return _cached
        except ImportError as exc:
            logger.info("Reranker backend %s unavailable: %s", backend.__name__, exc)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Reranker backend %s failed to load: %s", backend.__name__, exc)

    logger.info("No reranker available; retrieval order will be used as-is")
    return _cached


def reset_reranker_cache() -> None:
    global _cached, _attempted
    _cached, _attempted = None, False


def rerank(
    query: str, hits: Sequence[Hit], k: int, reranker: Optional[Reranker] = None
) -> Tuple[List[Hit], bool]:
    """Reorder candidates by cross-encoder score.

    Returns the reordered hits and whether reranking actually ran, so callers
    can apply the matching threshold: bi-encoder cosines and cross-encoder
    scores are different scales and must not share one cut-off.
    """
    reranker = reranker or get_reranker()
    if reranker is None or not hits:
        return list(hits)[:k], False

    try:
        scores = reranker.score(query, [h.passage.text for h in hits])
    except Exception as exc:  # noqa: BLE001
        # A reranking failure degrades to bi-encoder order rather than to no
        # answer at all.
        logger.warning("Reranking failed (%s); falling back to retrieval order", exc)
        return list(hits)[:k], False

    rescored = [
        Hit(Passage(**vars(h.passage)), round(score, 4))
        for h, score in zip(hits, scores)
    ]
    rescored.sort(key=lambda h: h.score, reverse=True)
    return rescored[:k], True
