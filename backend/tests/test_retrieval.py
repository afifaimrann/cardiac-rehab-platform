"""Retrieval quality, as an executable check rather than a claim.

These are the queries that caught real failures during development -- missing
stemming, and paraphrases the term index could not bridge. They exist so a
change to the tokenizer or the corpus cannot silently regress retrieval.
"""
import pytest

from app.services.retrieval import BM25Retriever, expand, stem, tokenize

retriever = BM25Retriever()

QUERIES = [
    ("how hard should I be exercising?", "How hard should I exercise?"),
    ("can I drive after my heart attack?", "Driving after a cardiac event"),
    ("my ankles are swollen in the evening", "Swollen ankles and legs"),
    ("when can I have sex again", "Resuming sexual activity"),
    ("I forgot to take my beta blocker", "Taking your medication"),
    ("what should I eat", "Eating for heart health"),
    ("how do I measure blood pressure properly", "How to measure your blood pressure at home"),
    ("am I allowed to go back to work", "Returning to work"),
    ("I feel low and anxious since my heart attack", "Mood after a cardiac event"),
    ("is it ok to drink wine", "Alcohol"),
    pytest.param(
        "how many times a week should I train", "How often and how long should I exercise?",
        marks=pytest.mark.xfail(
            reason="Lexical retrieval cannot reliably bridge 'train' -> 'exercise': the "
                   "synonym is downweighted (correctly, to stop generic terms dragging in "
                   "unrelated passages) and 'week'/'back' then favour the return-to-work "
                   "passage. This is the case the dense retriever is for.",
            strict=True,
        ),
    ),
    ("do I need to warm up", "Warming up and cooling down"),
    ("my wound is red and sore", "Caring for a surgical wound"),
    ("I want to quit cigarettes", "Stopping smoking"),
    ("I keep waking up at night", "Sleep and recovery"),
    ("what is a safe blood pressure", "Blood pressure in rehabilitation"),
    ("my weight went up 3 kg in two days", "Weight and fluid retention"),
    ("side effects of my tablets", "Common medication side effects"),
]


@pytest.mark.parametrize("query,expected_title", QUERIES)
def test_top_hit_is_the_right_passage(query, expected_title):
    hits = retriever.search(query, k=3)
    assert hits, f"no results for {query!r}"
    assert hits[0].passage.title == expected_title


def test_stemming_collapses_morphological_variants():
    assert stem("exercising") == stem("exercise")
    assert stem("eating") == stem("eat")
    assert stem("sexual") == stem("sex")
    assert stem("medications") == stem("medication")


def test_stopwords_are_dropped():
    assert tokenize("what should I do about the thing") == ["thing"]


def test_query_expansion_adds_weighted_synonyms():
    expanded = dict(expand(tokenize("I am anxious")))
    assert expanded[stem("anxious")] == 1.0          # the patient's own word
    assert 0 < expanded[stem("mood")] < 1.0          # a synonym, weighted lower


def test_an_unrelated_query_returns_nothing():
    assert retriever.search("quantum chromodynamics lattice gauge") == []


def test_scores_are_ordered():
    hits = retriever.search("blood pressure measurement at home", k=3)
    assert [h.score for h in hits] == sorted((h.score for h in hits), reverse=True)
