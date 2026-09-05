"""Reciprocal rank fusion."""
from app.services.fusion import reciprocal_rank_fusion
from app.services.knowledge import Passage
from app.services.retrieval import Hit


def hit(pid: str, score: float = 1.0) -> Hit:
    return Hit(Passage(id=pid, title=pid, source="test", text=pid), score)


def ids(fused):
    return [f.hit.passage.id for f in fused]


def test_agreement_beats_a_single_strong_result():
    """A passage both retrievers found should outrank one only one of them saw,
    even when that one was rank 1 on its own list."""
    lexical = [hit("a"), hit("b"), hit("c")]
    dense = [hit("d"), hit("b"), hit("e")]
    fused = reciprocal_rank_fusion(lexical, dense, k=3)
    assert ids(fused)[0] == "b"
    assert fused[0].found_by_both


def test_scores_do_not_need_to_be_comparable():
    """BM25 scores and cosine similarities live on different scales; fusion must
    depend only on rank order."""
    lexical = [hit("a", 87.5), hit("b", 40.0)]
    dense = [hit("b", 0.81), hit("a", 0.74)]
    by_rank = ids(reciprocal_rank_fusion(lexical, dense, k=2))

    lexical_rescaled = [hit("a", 0.9), hit("b", 0.4)]
    dense_rescaled = [hit("b", 810.0), hit("a", 740.0)]
    assert ids(reciprocal_rank_fusion(lexical_rescaled, dense_rescaled, k=2)) == by_rank


def test_one_empty_list_passes_the_other_through_in_order():
    lexical = [hit("a"), hit("b"), hit("c")]
    assert ids(reciprocal_rank_fusion(lexical, [], k=3)) == ["a", "b", "c"]
    assert ids(reciprocal_rank_fusion([], lexical, k=3)) == ["a", "b", "c"]


def test_both_empty_returns_nothing():
    assert reciprocal_rank_fusion([], [], k=5) == []


def test_result_is_capped_at_k():
    lexical = [hit(str(i)) for i in range(20)]
    dense = [hit(str(i)) for i in range(10, 30)]
    assert len(reciprocal_rank_fusion(lexical, dense, k=5)) == 5


def test_ranks_are_reported_for_explainability():
    fused = reciprocal_rank_fusion([hit("a"), hit("b")], [hit("b")], k=2)
    by_id = {f.hit.passage.id: f for f in fused}
    assert by_id["a"].lexical_rank == 1 and by_id["a"].dense_rank is None
    assert by_id["b"].lexical_rank == 2 and by_id["b"].dense_rank == 1


def test_rrf_constant_damps_the_top_rank():
    """With a small K the first rank dominates; with the standard K it does not."""
    lexical, dense = [hit("a"), hit("b")], [hit("b"), hit("c")]
    assert ids(reciprocal_rank_fusion(lexical, dense, k=1, rrf_k=1))[0] == "b"
    assert ids(reciprocal_rank_fusion(lexical, dense, k=1, rrf_k=60))[0] == "b"
