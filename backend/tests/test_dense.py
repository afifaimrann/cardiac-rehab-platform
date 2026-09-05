"""Dense retrieval over stored embeddings.

Uses the deterministic HashEmbedder so the storage and search paths are covered
without downloading a model. It is not semantic, so these tests assert plumbing
and ranking mechanics, not answer quality — retrieval quality lives in
test_retrieval.py.
"""
import pytest

from app.models.knowledge import KnowledgePassage
from app.services.dense import DenseRetriever, _cosine
from app.services.embeddings import HashEmbedder

embedder = HashEmbedder()

PASSAGES = [
    ("p1", "Exercise intensity", "Work at a moderate intensity during exercise sessions."),
    ("p2", "Blood pressure", "Measure blood pressure while seated and rested."),
    ("p3", "Medication", "Take cardiac medication exactly as prescribed each day."),
]


@pytest.fixture
async def stored(session_factory):
    async with session_factory() as db:
        vectors = embedder.encode([text for _, _, text in PASSAGES])
        for (key, title, text), vector in zip(PASSAGES, vectors):
            db.add(KnowledgePassage(
                passage_key=key, title=title, source="test", text=text,
                embedding=vector, embedding_model=embedder.name, embedding_dim=embedder.dim,
            ))
        await db.commit()
    return session_factory


def test_normalised_vectors_make_cosine_a_dot_product():
    a, b = embedder.encode(["blood pressure", "blood pressure"])
    assert _cosine(a, b) == pytest.approx(1.0, abs=1e-6)


def test_identical_text_scores_higher_than_unrelated_text():
    a, b, c = embedder.encode([
        "take cardiac medication as prescribed",
        "take cardiac medication as prescribed",
        "warm up before exercising",
    ])
    assert _cosine(a, b) > _cosine(a, c)


async def test_search_returns_stored_passages_ranked(stored):
    async with stored() as db:
        hits = await DenseRetriever(embedder).search(db, "blood pressure seated rested", k=3)
    assert hits
    assert hits[0].passage.id == "p2"
    assert [h.score for h in hits] == sorted((h.score for h in hits), reverse=True)


async def test_search_respects_k(stored):
    async with stored() as db:
        assert len(await DenseRetriever(embedder).search(db, "exercise", k=1)) == 1


async def test_rows_without_an_embedding_are_ignored(session_factory):
    async with session_factory() as db:
        db.add(KnowledgePassage(
            passage_key="unembedded", title="No vector", source="test",
            text="This row was never embedded.", embedding=None,
        ))
        await db.commit()
    async with session_factory() as db:
        assert await DenseRetriever(embedder).search(db, "anything", k=5) == []


async def test_rows_from_a_different_model_are_skipped_not_compared(session_factory):
    """A dimension mismatch must not crash or silently produce garbage scores."""
    async with session_factory() as db:
        db.add(KnowledgePassage(
            passage_key="wrong-dim", title="Other model", source="test",
            text="Embedded with a different model.",
            embedding=[0.1] * 99, embedding_model="other", embedding_dim=99,
        ))
        await db.commit()
    async with session_factory() as db:
        assert await DenseRetriever(embedder).search(db, "anything", k=5) == []


async def test_retriever_without_an_encoder_returns_nothing(stored):
    """No embedding backend installed is a supported state, not an error."""
    retriever = DenseRetriever(embedder=None)
    assert retriever.available is False
    async with stored() as db:
        assert await retriever.search(db, "blood pressure", k=3) == []
