"""Dense retrieval over stored passage embeddings.

Two execution paths, one behaviour:

  PostgreSQL   pgvector does the nearest-neighbour search in the database, using
               the cosine operator and an IVFFlat index. Work stays where the
               data is, and it keeps working as the corpus grows.
  Anything else  Vectors are loaded and scored in process. Correct and fast
               enough for a few thousand passages; the point is that tests and
               a local SQLite run need no extension.
"""
from __future__ import annotations

import logging
from typing import List, Optional, Sequence

from sqlalchemy import select, text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import KnowledgePassage
from app.services.embeddings import Embedder, get_embedder
from app.services.knowledge import Passage
from app.services.retrieval import Hit

logger = logging.getLogger("cardiac.dense")


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """Both sides are stored unit-normalised, so this is a dot product."""
    return sum(x * y for x, y in zip(a, b))


def _to_passage(row: KnowledgePassage) -> Passage:
    return Passage(id=row.passage_key, title=row.title, source=row.source, text=row.text)


class DenseRetriever:
    """Embedding search. Async because the vectors live in the database."""

    def __init__(self, embedder: Optional[Embedder] = None) -> None:
        self.embedder = embedder or get_embedder()

    @property
    def available(self) -> bool:
        return self.embedder is not None

    async def search(self, db: AsyncSession, query: str, k: int = 5) -> List[Hit]:
        if self.embedder is None:
            return []

        # Query-side encoding: asymmetric models need the query prefix.
        query_vector = self.embedder.encode_query(query)

        if db.bind is not None and db.bind.dialect.name == "postgresql":
            return await self._search_pgvector(db, query_vector, k)
        return await self._search_in_process(db, query_vector, k)

    async def _search_pgvector(
        self, db: AsyncSession, query_vector: List[float], k: int
    ) -> List[Hit]:
        # `<=>` is pgvector's cosine distance: 0 is identical, 2 is opposite.
        # Converted to a similarity so callers see one scale across both paths.
        statement = sql_text(
            """
            SELECT passage_key, title, source, text,
                   1 - (embedding <=> CAST(:query AS vector)) AS similarity
            FROM knowledge_passages
            WHERE embedding IS NOT NULL
            ORDER BY embedding <=> CAST(:query AS vector)
            LIMIT :k
            """
        )
        result = await db.execute(
            statement, {"query": str(list(query_vector)), "k": k}
        )
        return [
            Hit(
                Passage(id=row.passage_key, title=row.title, source=row.source, text=row.text),
                round(float(row.similarity), 4),
            )
            for row in result
        ]

    async def _search_in_process(
        self, db: AsyncSession, query_vector: List[float], k: int
    ) -> List[Hit]:
        result = await db.execute(
            select(KnowledgePassage).where(KnowledgePassage.embedding.is_not(None))
        )
        scored: List[Hit] = []
        for row in result.scalars().all():
            vector = row.embedding
            if not vector or len(vector) != len(query_vector):
                # A row embedded with a different model is skipped rather than
                # compared against incompatible dimensions.
                continue
            scored.append(Hit(_to_passage(row), round(_cosine(query_vector, vector), 4)))

        scored.sort(key=lambda h: h.score, reverse=True)
        return scored[:k]
