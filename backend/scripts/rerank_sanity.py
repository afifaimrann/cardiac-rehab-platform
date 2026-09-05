# -*- coding: utf-8 -*-
"""Is the reranker actually loaded, or is its classification head untrained?

A cross-encoder whose scoring head was randomly initialised still runs, still
returns numbers, and still orders things -- arbitrarily. This checks the model
against pairs whose answer is not in doubt.

    python -m scripts.rerank_sanity
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Surface the "newly initialized" warning transformers emits when a head is not
# found in the checkpoint. That single line is usually the whole answer.
logging.basicConfig(level=logging.INFO)
import transformers  # noqa: E402

transformers.logging.set_verbosity_info()

from app.core.config import settings  # noqa: E402

OBVIOUS_PAIRS = [
    ("Can I drive after my heart attack?",
     "There is usually a minimum period before you may drive again, and it differs "
     "by event, by treatment, and by licence type, with longer restrictions for "
     "vocational licences.", "should be HIGH"),
    ("Can I drive after my heart attack?",
     "Bananas are a good source of potassium and grow in tropical climates.",
     "should be LOW"),
    ("What is the capital of Mongolia?",
     "There is usually a minimum period before you may drive again after a "
     "cardiac event.", "should be LOW"),
    ("how much exercise should I do",
     "A typical starting prescription is three sessions a week of about 30 "
     "minutes, which may be broken into shorter blocks.", "should be HIGH"),
]


def check(label: str, scorer) -> bool:
    print(f"\n=== {label} ===")
    values = scorer.score_all(OBVIOUS_PAIRS)
    for (query, _passage, expectation), value in zip(OBVIOUS_PAIRS, values):
        print(f"  {value:8.4f}   {expectation:16}  {query[:46]}")

    high = [values[0], values[3]]
    low = [values[1], values[2]]
    separated = min(high) > max(low) + 0.2
    print("  -> " + (
        "separated: this backend is scoring correctly."
        if separated else
        "NOT separated: this backend's scores are unusable."
    ))
    return separated


class _Flag:
    def __init__(self):
        from app.services.reranking import FlagEmbeddingReranker

        self._impl = FlagEmbeddingReranker()
        self.name = self._impl.name

    def score_all(self, pairs):
        return self._impl.score(pairs[0][0], [pairs[0][1]]) + [
            self._impl.score(q, [p])[0] for q, p, _ in pairs[1:]
        ]


class _Transformers:
    def __init__(self):
        from app.services.reranking import TransformersReranker

        self._impl = TransformersReranker()
        self.name = self._impl.name

    def score_all(self, pairs):
        # One query at a time, matching how it is called in production.
        return [self._impl.score(q, [p])[0] for q, p, _ in pairs]


class _CrossEncoder:
    def __init__(self):
        from app.services.reranking import CrossEncoderReranker

        self._impl = CrossEncoderReranker()
        self.name = self._impl.name

    def score_all(self, pairs):
        return [self._impl.score(q, [p])[0] for q, p, _ in pairs]


def main() -> int:
    print(f"\nModel: {settings.RERANKER_MODEL}")
    print("Scoring four pairs whose correct answer is not in doubt.\n")

    results = {}
    for label, factory in (
        ("FlagEmbedding", _Flag),
        ("transformers", _Transformers),
        ("sentence-transformers", _CrossEncoder),
    ):
        try:
            results[label] = check(label, factory())
        except Exception as exc:  # noqa: BLE001
            print(f"\n=== {label} ===\n  unavailable: {exc}")

    print("\n--- verdict ---")
    working = [name for name, ok in results.items() if ok]
    if working:
        print(f"  Use: {', '.join(working)}")
        print("  Set RERANKER_BACKEND in .env to the one you want.")
    else:
        print("  Neither backend separates relevant from irrelevant pairs.")
        print("  Set RERANK_ENABLED=false and rely on bi-encoder retrieval until this is resolved.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
