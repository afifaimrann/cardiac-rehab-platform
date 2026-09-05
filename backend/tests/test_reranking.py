"""Cross-encoder reranking.

Uses a stub reranker so the ordering, thresholding and fallback logic are
covered without downloading a cross-encoder. Real reranking quality is measured
by `scripts/retrieval_debug.py --rerank` against the live model.
"""
from typing import List, Sequence

from app.services.knowledge import Passage
from app.services.reranking import rerank
from app.services.retrieval import Hit


def hit(pid: str, score: float, text: str = "") -> Hit:
    return Hit(Passage(id=pid, title=pid, source="test", text=text or pid), score)


class StubReranker:
    """Scores by a lookup table, so tests state the intended ordering directly."""

    name = "stub"

    def __init__(self, scores: dict) -> None:
        self._scores = scores

    def score(self, query: str, passages: Sequence[str]) -> List[float]:
        return [self._scores.get(p, 0.0) for p in passages]


class BrokenReranker:
    name = "broken"

    def score(self, query: str, passages: Sequence[str]) -> List[float]:
        raise RuntimeError("model unavailable")


def test_reranking_reorders_by_cross_encoder_score():
    """The bi-encoder's first choice is not necessarily the best one."""
    hits = [hit("a", 0.66), hit("b", 0.65), hit("c", 0.64)]
    reranker = StubReranker({"a": 0.10, "b": 0.95, "c": 0.40})

    reranked, ran = rerank("q", hits, k=3, reranker=reranker)
    assert ran
    assert [h.passage.id for h in reranked] == ["b", "c", "a"]


def test_scores_are_replaced_not_blended():
    """Cross-encoder scores are on their own scale; mixing them with cosines
    would make any threshold meaningless."""
    reranked, _ = rerank("q", [hit("a", 0.66)], k=1, reranker=StubReranker({"a": 0.95}))
    assert reranked[0].score == 0.95


def test_result_is_capped_at_k():
    hits = [hit(str(i), 0.5) for i in range(20)]
    scores = {str(i): i / 20 for i in range(20)}
    reranked, _ = rerank("q", hits, k=3, reranker=StubReranker(scores))
    assert len(reranked) == 3
    assert [h.passage.id for h in reranked] == ["19", "18", "17"]


def test_missing_reranker_passes_hits_through_unchanged():
    """No reranker installed is a supported state, not an error."""
    hits = [hit("a", 0.66), hit("b", 0.65)]
    passed, ran = rerank("q", hits, k=5, reranker=None)
    assert ran is False
    assert [h.passage.id for h in passed] == ["a", "b"]
    assert passed[0].score == 0.66      # original scores preserved


def test_reranker_failure_degrades_to_retrieval_order():
    """A model error must cost ordering quality, not the answer."""
    hits = [hit("a", 0.66), hit("b", 0.65)]
    passed, ran = rerank("q", hits, k=5, reranker=BrokenReranker())
    assert ran is False
    assert [h.passage.id for h in passed] == ["a", "b"]


def test_empty_candidate_list_is_handled():
    assert rerank("q", [], k=5, reranker=StubReranker({})) == ([], False)


def test_original_passages_are_not_mutated():
    """Reranking must not write its scores back onto the retrieved objects."""
    original = hit("a", 0.66)
    rerank("q", [original], k=1, reranker=StubReranker({"a": 0.95}))
    assert original.score == 0.66


class RawLogitReranker:
    """Emits unbounded logits, as a cross-encoder without an output activation
    would."""

    name = "logits"

    def __init__(self, values: List[float]) -> None:
        self._values = values

    def score(self, query: str, passages: Sequence[str]) -> List[float]:
        import math

        raw = self._values[: len(passages)]
        if all(0.0 <= v <= 1.0 for v in raw):
            return raw
        return [1.0 / (1.0 + math.exp(-v)) for v in raw]


def test_probability_scores_are_not_squashed_again():
    """Regression: applying sigmoid to values already in [0,1] mapped every
    score into [0.5, 0.73] and destroyed the separation the reranker exists to
    provide."""
    from app.services.reranking import CrossEncoderReranker

    scorer = CrossEncoderReranker.__new__(CrossEncoderReranker)

    class FakeModel:
        def predict(self, pairs):
            return [0.99, 0.01, 0.5][: len(pairs)]

    scorer._model = FakeModel()
    scorer.name = "fake"

    scores = scorer.score("q", ["a", "b", "c"])
    assert scores == [0.99, 0.01, 0.5]
    assert max(scores) - min(scores) > 0.9      # separation survives


def test_raw_logits_are_passed_through_a_sigmoid():
    from app.services.reranking import CrossEncoderReranker

    scorer = CrossEncoderReranker.__new__(CrossEncoderReranker)

    class FakeModel:
        def predict(self, pairs):
            return [8.0, -8.0][: len(pairs)]

    scorer._model = FakeModel()
    scorer.name = "fake"

    scores = scorer.score("q", ["a", "b"])
    assert scores[0] > 0.99 and scores[1] < 0.01
