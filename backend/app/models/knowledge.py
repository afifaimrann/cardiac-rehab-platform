"""Stored corpus passages and their embeddings.

The embedding column is a real `vector` on PostgreSQL (pgvector) and JSON
everywhere else. That keeps `pytest` running on SQLite with no extension while
production gets an indexed nearest-neighbour search, and it means the ingest
code and the models are identical on both.
"""
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.base import Base, Timestamped, UUIDPrimaryKey

# pgvector is optional: without it the JSON column is used everywhere and search
# falls back to in-process cosine, which is fine for a corpus of this size.
try:  # pragma: no cover - depends on the deployment
    from pgvector.sqlalchemy import Vector

    PGVECTOR_AVAILABLE = True
except ImportError:  # pragma: no cover
    Vector = None  # type: ignore[assignment]
    PGVECTOR_AVAILABLE = False

# Dimension of the configured model (bge-small-en-v1.5 = 384, bge-m3 = 1024).
# The model name is stored per row, so a mismatch after a model change is
# detectable rather than silently producing nonsense similarities.
from app.core.config import settings  # noqa: E402

EMBEDDING_DIM = settings.EMBEDDING_DIM

if PGVECTOR_AVAILABLE:
    EmbeddingColumn: Any = JSON().with_variant(Vector(EMBEDDING_DIM), "postgresql")
else:  # pragma: no cover
    EmbeddingColumn = JSON()


class KnowledgePassage(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "knowledge_passages"
    __table_args__ = (
        Index("ix_knowledge_passage_key", "passage_key", unique=True),
        Index("ix_knowledge_model", "embedding_model"),
    )

    # Stable identifier from the corpus (e.g. "medlineplus/heart-attack#2"),
    # so a re-ingest updates rows in place instead of duplicating them.
    passage_key: Mapped[str] = mapped_column(String(200), nullable=False)

    title: Mapped[str] = mapped_column(String(300), nullable=False)
    source: Mapped[str] = mapped_column(String(500), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)

    embedding_model: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    embedding_dim: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    embedding: Mapped[Optional[Any]] = mapped_column(EmbeddingColumn, nullable=True)
