# -*- coding: utf-8 -*-
"""Inspect retrieval scores, to calibrate MIN_DENSE_SIMILARITY.

The right threshold is model-dependent and cannot be guessed: it sits between
the score a relevant passage gets and the score an unrelated one gets, and both
numbers move when the encoder changes.

Run it, look at the gap, and set MIN_DENSE_SIMILARITY in .env just below the
weakest score you would still want answered.

    python -m scripts.retrieval_debug
    python -m scripts.retrieval_debug "আমার ওষুধ খেতে ভুলে গেছি"
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings  # noqa: E402
from app.db.session import AsyncSessionLocal, engine  # noqa: E402
from app.services.dense import DenseRetriever  # noqa: E402
from app.services.language import detect_script  # noqa: E402
from app.services.reranking import get_reranker, rerank  # noqa: E402
from app.services.retrieval import retriever as lexical_retriever  # noqa: E402

# Questions that SHOULD retrieve something, and nonsense that should not.
# The threshold belongs in the gap between the two groups.
DEFAULT_QUERIES: List[tuple[str, bool]] = [
    ("How hard should I be exercising?", True),
    ("Can I drive after my heart attack?", True),
    ("I forgot to take my medication", True),
    ("আমি কি হাঁটতে পারব?", True),
    ("ওষুধ খেতে ভুলে গেছি", True),
    ("ব্যায়াম কতটুকু করা উচিত?", True),
    ("আমার রক্তচাপ কত হওয়া উচিত?", True),
    ("ধূমপান ছাড়তে চাই", True),
    ("কাজে ফিরে যেতে পারব কবে?", True),
    ("What is the capital of Mongolia?", False),
    ("সবচেয়ে ভালো ক্রিকেট খেলোয়াড় কে?", False),
    ("how do I fix a bicycle puncture", False),
]


async def main() -> int:
    queries = (
        [(q, True) for q in sys.argv[1:]] if len(sys.argv) > 1 else DEFAULT_QUERIES
    )

    dense = DenseRetriever()
    if not dense.available:
        print("No embedding backend available. Check EMBEDDING_BACKEND in .env.")
        return 1

    reranker = get_reranker()
    threshold = settings.MIN_RERANK_SCORE if reranker else settings.MIN_DENSE_SIMILARITY
    setting_name = "MIN_RERANK_SCORE" if reranker else "MIN_DENSE_SIMILARITY"

    print(f"Encoder:   {dense.embedder.name}")
    print(f"Reranker:  {reranker.name if reranker else 'none'}")
    print(f"Threshold: {setting_name} = {threshold}\n")

    relevant_scores: List[float] = []
    irrelevant_scores: List[float] = []

    async with AsyncSessionLocal() as db:
        for query, should_match in queries:
            candidates = await dense.search(
                db, query, k=settings.RERANK_CANDIDATES if reranker else 3
            )
            script = detect_script(query).value
            marker = "expected match" if should_match else "expected NO match"
            print(f"{query}   [{script}, {marker}]")

            if not candidates:
                print("    (nothing stored, or no neighbours)\n")
                continue

            if reranker:
                before = [(h.passage.title, h.score) for h in candidates[:3]]
                hits, _ = rerank(query, candidates, k=3, reranker=reranker)
                print("    bi-encoder:")
                for title, score in before:
                    print(f"        {score:6.3f}         {title}")
                print("    after reranking:")
            else:
                hits = candidates[:3]

            for hit in hits:
                kept = "keep" if hit.score >= threshold else "drop"
                print(f"        {hit.score:6.3f}  {kept:5}  {hit.passage.title}")

            (relevant_scores if should_match else irrelevant_scores).append(hits[0].score)

            # Lexical scores are on a different scale entirely; shown only to
            # make the point that the two cannot be compared directly.
            if script == "latin":
                lex = lexical_retriever.search(query, k=1)
                if lex:
                    print(f"    (bm25 top: {lex[0].score:.2f} — different scale, not comparable)")
            print()

    if relevant_scores and irrelevant_scores:
        worst_relevant = min(relevant_scores)
        best_irrelevant = max(irrelevant_scores)
        print("-" * 70)
        print(f"Weakest score among questions that should match: {worst_relevant:.3f}")
        print(f"Strongest score among questions that should not: {best_irrelevant:.3f}")
        margin = worst_relevant - best_irrelevant
        print(f"Margin between the two groups:                   {margin:+.3f}")

        if margin > 0.15:
            suggested = round((worst_relevant + best_irrelevant) / 2, 2)
            print(f"\nWide separation. Set {setting_name} = {suggested}")
        elif margin > 0:
            suggested = round((worst_relevant + best_irrelevant) / 2, 2)
            print(
                f"\nSeparation is real but narrow ({margin:.3f}). {setting_name} = "
                f"{suggested} works for these queries, but a query not in this set "
                "could easily fall the wrong side of it. Treat it as provisional."
            )
        else:
            print(
                "\nNo clean separation: some irrelevant passages score higher than "
                "some relevant ones.\nNo threshold fixes that — it means the corpus "
                "lacks an answer for one of these\nquestions, or the encoder is not "
                "bridging the language gap."
            )

    await engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
