"""The checks that run before the API accepts a request.

Both exist because of failures that are worse than a crash: a schema that is
silently out of date, and a corpus that is silently empty. Neither stops the
server starting, so neither announces itself unless something makes it.
"""
import logging

import pytest
from sqlalchemy import insert

from app.main import warn_if_corpus_empty
from app.models.knowledge import KnowledgePassage


@pytest.fixture
def engine_bound_to_test_db(db_engine, monkeypatch):
    """Point the startup check at the test database rather than the real one."""
    import app.main as main

    monkeypatch.setattr(main, "engine", db_engine)
    return db_engine


async def test_empty_corpus_warns_with_the_command_that_fixes_it(
    engine_bound_to_test_db, caplog
):
    """An empty corpus makes the assistant answer "I don't have guidance on
    that" to every question. That looks like a bad model rather than a missing
    setup step, so the warning has to name the script."""
    with caplog.at_level(logging.WARNING, logger="cardiac"):
        await warn_if_corpus_empty()

    warnings = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert warnings, "an empty corpus must warn"
    assert "EMPTY" in warnings[0]
    assert "scripts.embed_corpus" in warnings[0], "the warning must say how to fix it"


async def test_a_populated_corpus_does_not_warn(engine_bound_to_test_db, caplog):
    async with engine_bound_to_test_db.begin() as conn:
        await conn.execute(insert(KnowledgePassage).values(
            id="p1", passage_key="handbook:return-to-work:0",
            title="Returning to work", source="Programme handbook",
            text="Most people return to work within four to twelve weeks.",
        ))

    with caplog.at_level(logging.INFO, logger="cardiac"):
        await warn_if_corpus_empty()

    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("1 passages" in r.getMessage() for r in caplog.records)
