"""Chunk the corpus, embed it, and store it for retrieval.

Idempotent: passages are upserted by their stable key, so re-running after a
corpus refresh updates rows in place rather than duplicating them, and rows
whose source passage has disappeared are removed.

    python -m scripts.embed_corpus
    python -m scripts.embed_corpus --backend hash     # no model download
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import delete, select  # noqa: E402

from app.db.session import AsyncSessionLocal, engine  # noqa: E402
from app.models.knowledge import KnowledgePassage  # noqa: E402
from app.services.corpus import DEFAULT_CORPUS_DIR, load_corpus  # noqa: E402
from app.services.embeddings import get_embedder  # noqa: E402

BATCH_SIZE = 64


async def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS_DIR)
    parser.add_argument("--backend", default=None,
                        help="Force an embedding backend (fastembed, openai, hash, ...)")
    parser.add_argument("--prune", action="store_true", default=True,
                        help="Delete stored passages no longer present in the corpus")
    args = parser.parse_args(argv)

    passages = load_corpus(args.corpus)
    print(f"Corpus: {len(passages)} passages")

    embedder = get_embedder(force=args.backend)
    if embedder is None:
        print(
            "No embedding backend available.\n"
            "Install one (pip install fastembed) or pass --backend hash for a\n"
            "dependency-free run that exercises the pipeline without semantics.",
            file=sys.stderr,
        )
        return 1
    print(f"Encoder: {embedder.name} (dim={embedder.dim})")

    async with AsyncSessionLocal() as db:
        existing = {
            row.passage_key: row
            for row in (await db.execute(select(KnowledgePassage))).scalars().all()
        }

        created = updated = 0
        for start in range(0, len(passages), BATCH_SIZE):
            batch = passages[start:start + BATCH_SIZE]
            vectors = embedder.encode([p.text for p in batch])

            for passage, vector in zip(batch, vectors):
                row = existing.get(passage.id)
                if row is None:
                    db.add(KnowledgePassage(
                        passage_key=passage.id, title=passage.title, source=passage.source,
                        text=passage.text, embedding=vector,
                        embedding_model=embedder.name, embedding_dim=embedder.dim,
                    ))
                    created += 1
                else:
                    row.title = passage.title
                    row.source = passage.source
                    row.text = passage.text
                    row.embedding = vector
                    row.embedding_model = embedder.name
                    row.embedding_dim = embedder.dim
                    updated += 1

            # Commit each batch rather than accumulating every row for one
            # flush at the end: progress is durable, an interrupt loses at most
            # one batch, and the run cannot appear to hang on a final commit.
            await db.commit()
            done = min(start + BATCH_SIZE, len(passages))
            print(f"  embedded and saved {done}/{len(passages)}", flush=True)

        removed = 0
        if args.prune:
            current_keys = {p.id for p in passages}
            stale = [key for key in existing if key not in current_keys]
            if stale:
                await db.execute(
                    delete(KnowledgePassage).where(KnowledgePassage.passage_key.in_(stale))
                )
                removed = len(stale)

        await db.commit()

    print(f"\nCreated {created}, updated {updated}, removed {removed}")
    await engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
