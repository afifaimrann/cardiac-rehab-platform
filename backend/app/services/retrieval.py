"""Retrieval over the guidance corpus.

BM25, implemented here in ~60 lines rather than pulled in as a dependency. For a
corpus of this size that is the right tool: it needs no model, no vector store
and no API key, it runs in microseconds, and its scores are inspectable -- when
a wrong passage is retrieved you can see exactly which term caused it.

`Retriever` is a Protocol so a dense/embedding retriever can be substituted
without touching the chat service. That swap is worth making when the corpus
outgrows keyword matching -- typically when paraphrase-heavy questions start
missing (a patient asking about "the pill that makes me tired" will not match
"beta blocker" on terms alone).
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Dict, List, Protocol, Sequence, Tuple

from app.services.knowledge import CORPUS, Passage

# Very common words carry no discriminative signal in a corpus this small.
STOPWORDS = frozenset("""
a about again all also am an and any are as at be been being but by can could did do
does doing done down each few for from get got had has have having here how i if in
into is it its just like may me more most much must my no not now of on only or other
our out over own same should so some still such than that the their them then there
these they this those to too up very was we were what when where which while who why
will with would you your
""".split())

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# Suffix rules, longest first. Not a full Porter stemmer -- just enough to make
# morphological variants collide, which is where keyword retrieval actually
# fails in practice: "exercising" must match "exercise", "eat" must match
# "eating", and "sex" must match "sexual".
_SUFFIXES = (
    ("ations", "ate"), ("ation", "ate"), ("ually", "ual"), ("ually", "ual"),
    ("iness", "y"), ("ingly", ""), ("edly", ""),
    ("ings", ""), ("ing", ""), ("ies", "y"), ("ied", "y"),
    ("ual", ""), ("ally", ""), ("ely", ""), ("ly", ""),
    ("ers", ""), ("er", ""), ("est", ""),
    ("ess", ""), ("es", ""), ("ed", ""), ("s", ""),
)

# Words whose stems would collide unhelpfully or which read wrong when trimmed.
_STEM_EXCEPTIONS = {
    "stress": "stress", "less": "less", "press": "press", "process": "process",
    "illness": "ill", "wellness": "well", "was": "was", "his": "his",
    "this": "this", "as": "as", "is": "is", "gas": "gas",
}


def stem(word: str) -> str:
    if word in _STEM_EXCEPTIONS:
        return _STEM_EXCEPTIONS[word]
    for suffix, replacement in _SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            word = word[: -len(suffix)] + replacement
            break
    # Drop a trailing silent "e" so "exercise" and "exercising" land on the same
    # stem. Applied last, and only to longer words, so "ate"/"are" survive.
    if len(word) >= 5 and word.endswith("e"):
        word = word[:-1]
    return word


# Query-side expansion for terms patients and documents express differently.
# Keyword retrieval cannot bridge these on its own, and every pair below comes
# from an observed miss rather than from guessing. Keys are stemmed at import
# so lookup happens in the same space as the tokens.
_RAW_SYNONYMS: Dict[str, tuple] = {
    # mood
    "anxious": ("anxiety", "mood", "low"),
    "anxiety": ("mood", "low"),
    "worried": ("anxiety", "mood"),
    "depressed": ("mood", "low"),
    "sad": ("mood", "low"),
    "panic": ("anxiety", "mood"),
    # sleep
    "waking": ("sleep", "sleepiness"),
    "awake": ("sleep",),
    "night": ("sleep",),
    "insomnia": ("sleep",),
    "snore": ("sleep", "snoring"),
    # symptoms
    "dizzy": ("dizziness", "faint"),
    "breathless": ("breath", "breathe"),
    "puffy": ("swelling", "swollen"),
    "tired": ("tiredness", "fatigue"),
    "exhausted": ("tiredness",),
    # medication
    "pill": ("medication", "dose"),
    "pills": ("medication", "dose"),
    "tablet": ("medication", "dose"),
    "drug": ("medication",),
    "meds": ("medication",),
    # lifestyle
    "wine": ("alcohol", "drink"),
    "beer": ("alcohol", "drink"),
    "booze": ("alcohol", "drink"),
    "cigarette": ("smoking", "smoke"),
    "cigarettes": ("smoking", "smoke"),
    "vape": ("smoking",),
    "quit": ("stopping", "stop"),
    # activity
    "train": ("exercise", "session"),
    "training": ("exercise", "session"),
    "workout": ("exercise", "session"),
    "gym": ("exercise", "activity"),
    "jog": ("exercise", "activity"),
    "walking": ("exercise", "activity"),
    # abbreviations
    "bp": ("blood", "pressure"),
    "hr": ("heart", "rate"),
    "rpe": ("borg", "exertion"),
}


def _build_synonym_index() -> Dict[str, tuple]:
    index: Dict[str, tuple] = {}
    for word, extras in _RAW_SYNONYMS.items():
        index.setdefault(stem(word), ())
        index[stem(word)] += tuple(stem(e) for e in extras)
    return index


SYNONYMS: Dict[str, tuple] = _build_synonym_index()


def expand(tokens: List[str]) -> List[Tuple[str, float]]:
    """Weight a query's terms: the patient's own words at full weight, synonym
    terms below. Expansion is applied to queries only, never to documents, so
    corpus statistics stay honest and only the query broadens."""
    weighted: List[Tuple[str, float]] = [(t, 1.0) for t in tokens]
    seen = set(tokens)
    for token in tokens:
        for extra in SYNONYMS.get(token, ()):
            if extra not in seen:
                seen.add(extra)
                weighted.append((extra, EXPANSION_WEIGHT))
    return weighted

K1 = 1.5   # term-frequency saturation
B = 0.75   # length normalisation

# Synonym terms score lower than the patient's own words. Without this, one
# generic expanded term can outrank the actual question: "I forgot to take my
# meds" expanded "meds" to "medication" and pulled in the passage on resuming
# sexual activity, which mentions medication only inside a nitrates warning.
EXPANSION_WEIGHT = 0.35

# A hit must also reach this fraction of the best score to be shown at all.
# Absolute scores vary with query length; the ratio does not.
MIN_SCORE_RATIO = 0.5


def tokenize(text: str) -> List[str]:
    return [
        stem(t)
        for t in _TOKEN_RE.findall(text.lower())
        if t not in STOPWORDS and len(t) > 1
    ]


@dataclass(frozen=True)
class Hit:
    passage: Passage
    score: float


class Retriever(Protocol):
    def search(self, query: str, k: int = 3) -> List[Hit]: ...


class BM25Retriever:
    def __init__(self, corpus: Sequence[Passage] = CORPUS) -> None:
        self.corpus = list(corpus)
        # Title terms are indexed twice: a passage titled "Chest pain and angina"
        # should win a question about chest pain over one that merely mentions it.
        self.docs = [Counter(tokenize(p.title) * 2 + tokenize(p.text)) for p in self.corpus]
        self.lengths = [sum(d.values()) for d in self.docs]
        self.avg_length = (sum(self.lengths) / len(self.lengths)) if self.lengths else 0.0

        df: Counter = Counter()
        for doc in self.docs:
            df.update(doc.keys())
        n = len(self.docs)
        self.idf: Dict[str, float] = {
            term: math.log(1 + (n - count + 0.5) / (count + 0.5)) for term, count in df.items()
        }

    def search(self, query: str, k: int = 3) -> List[Hit]:
        terms = expand(tokenize(query))
        if not terms:
            return []

        scored: List[Hit] = []
        for passage, doc, length in zip(self.corpus, self.docs, self.lengths):
            score = 0.0
            for term, weight in terms:
                tf = doc.get(term, 0)
                if not tf:
                    continue
                norm = 1 - B + B * (length / self.avg_length if self.avg_length else 1)
                score += weight * self.idf.get(term, 0.0) * (tf * (K1 + 1)) / (tf + K1 * norm)
            if score > 0:
                scored.append(Hit(passage, round(score, 4)))

        if not scored:
            return []

        scored.sort(key=lambda h: h.score, reverse=True)
        # Drop hits far weaker than the best one: three weak passages read as
        # three answers, and a patient cannot tell which to trust.
        floor = scored[0].score * MIN_SCORE_RATIO
        return [h for h in scored if h.score >= floor][:k]


retriever: Retriever = BM25Retriever()
