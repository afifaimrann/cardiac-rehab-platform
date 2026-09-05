"""Reciprocal rank fusion of lexical and dense results.

BM25 scores and cosine similarities are not comparable — different scales,
different distributions — so they are fused by *rank* rather than by score.
Each list contributes 1/(K + rank) per passage, and passages both retrievers
agree on rise to the top.

K = 60 is the constant from the original RRF paper. It damps the influence of
the very top rank, so one retriever cannot dominate on a query the other
understands better, which is the whole reason for running both.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence

from app.services.retrieval import Hit

RRF_K = 60


@dataclass(frozen=True)
class FusedHit:
    hit: Hit
    score: float
    lexical_rank: int | None
    dense_rank: int | None

    @property
    def found_by_both(self) -> bool:
        return self.lexical_rank is not None and self.dense_rank is not None


def reciprocal_rank_fusion(
    lexical: Sequence[Hit], dense: Sequence[Hit], k: int = 5, rrf_k: int = RRF_K
) -> List[FusedHit]:
    scores: Dict[str, float] = {}
    lexical_ranks: Dict[str, int] = {}
    dense_ranks: Dict[str, int] = {}
    passages: Dict[str, Hit] = {}

    for rank, hit in enumerate(lexical, start=1):
        key = hit.passage.id
        scores[key] = scores.get(key, 0.0) + 1.0 / (rrf_k + rank)
        lexical_ranks[key] = rank
        passages.setdefault(key, hit)

    for rank, hit in enumerate(dense, start=1):
        key = hit.passage.id
        scores[key] = scores.get(key, 0.0) + 1.0 / (rrf_k + rank)
        dense_ranks[key] = rank
        passages.setdefault(key, hit)

    fused = [
        FusedHit(
            hit=passages[key],
            score=round(score, 6),
            lexical_rank=lexical_ranks.get(key),
            dense_rank=dense_ranks.get(key),
        )
        for key, score in scores.items()
    ]
    # Ties broken toward agreement: a passage both retrievers found beats one
    # only a single retriever saw at the same fused score.
    fused.sort(key=lambda f: (f.score, f.found_by_both), reverse=True)
    return fused[:k]
