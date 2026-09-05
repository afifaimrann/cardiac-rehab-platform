"""Script detection, used to route retrieval and to steer generation.

Deliberately script detection rather than language identification: it needs no
model, cannot be wrong about Bengali vs Latin, and the distinction that matters
here is exactly whether the lexical index can do anything useful with the query.
"""
from __future__ import annotations

from enum import Enum

# Bengali block, plus the Bengali-specific supplement.
BENGALI_RANGE = ((0x0980, 0x09FF),)
LATIN_RANGES = ((0x0041, 0x005A), (0x0061, 0x007A))

# Below this share of Bengali characters a query is treated as English with
# stray characters rather than as a Bengali question.
BENGALI_THRESHOLD = 0.20


class Script(str, Enum):
    BENGALI = "bengali"
    LATIN = "latin"
    MIXED = "mixed"
    UNKNOWN = "unknown"


def _in_ranges(char: str, ranges) -> bool:
    code = ord(char)
    return any(low <= code <= high for low, high in ranges)


def bengali_ratio(text: str) -> float:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    bengali = sum(1 for c in letters if _in_ranges(c, BENGALI_RANGE))
    return bengali / len(letters)


def detect_script(text: str) -> Script:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return Script.UNKNOWN

    bengali = sum(1 for c in letters if _in_ranges(c, BENGALI_RANGE))
    latin = sum(1 for c in letters if _in_ranges(c, LATIN_RANGES))
    ratio = bengali / len(letters)

    if ratio >= 0.8:
        return Script.BENGALI
    if ratio >= BENGALI_THRESHOLD and latin:
        # Code-switched: "আমার chest pain হচ্ছে" is extremely common and must be
        # treated as Bengali for routing, not as English with decoration.
        return Script.MIXED
    if ratio >= BENGALI_THRESHOLD:
        return Script.BENGALI
    return Script.LATIN if latin else Script.UNKNOWN


def uses_bengali(text: str) -> bool:
    return detect_script(text) in (Script.BENGALI, Script.MIXED)
