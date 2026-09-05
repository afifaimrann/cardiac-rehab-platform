"""Corpus loading and chunking.

Documents are data on disk, not literals in Python, so the knowledge base can
grow without a code change and its provenance is recorded per document. A
document without a licence and a source URL is refused: an unattributed passage
that reaches a patient-facing answer is a problem no amount of retrieval quality
makes up for.

The hand-written passages in `knowledge.py` remain the built-in fallback so the
system answers something sensible before any corpus is fetched.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, List, Optional, Sequence

from app.services.knowledge import CORPUS as BUILTIN_CORPUS, Passage

logger = logging.getLogger("cardiac.corpus")

DEFAULT_CORPUS_DIR = Path(__file__).resolve().parents[2] / "corpus"

# Chunk sizes in characters. Long enough to carry an idea, short enough that a
# retrieved passage is readable in a chat bubble without scrolling.
TARGET_CHARS = 900
MAX_CHARS = 1400
MIN_CHARS = 250
OVERLAP_SENTENCES = 1

REQUIRED_FIELDS = ("id", "title", "text", "source", "source_url", "licence")

_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")


class CorpusError(ValueError):
    """A document is malformed or missing its provenance."""


@dataclass(frozen=True)
class Document:
    id: str
    title: str
    text: str
    source: str
    source_url: str
    licence: str
    attribution: Optional[str] = None


def _split_sentences(text: str) -> List[str]:
    return [s.strip() for s in _SENTENCE_RE.split(text) if s.strip()]


def chunk_text(text: str, title: str) -> List[str]:
    """Split on paragraphs, then pack paragraphs up to the target size.

    Paragraph boundaries are respected because they are real semantic breaks in
    this material; an oversized paragraph is split on sentences, with one
    sentence of overlap so an idea spanning the boundary is retrievable from
    either side.
    """
    chunks: List[str] = []
    buffer = ""

    def flush() -> None:
        nonlocal buffer
        if buffer.strip():
            chunks.append(buffer.strip())
        buffer = ""

    for paragraph in (p.strip() for p in text.split("\n\n") if p.strip()):
        if len(paragraph) > MAX_CHARS:
            flush()
            sentences = _split_sentences(paragraph)
            current: List[str] = []
            for sentence in sentences:
                candidate = " ".join(current + [sentence])
                if current and len(candidate) > TARGET_CHARS:
                    chunks.append(" ".join(current))
                    current = current[-OVERLAP_SENTENCES:] + [sentence]
                else:
                    current.append(sentence)
            if current:
                chunks.append(" ".join(current))
            continue

        if buffer and len(buffer) + len(paragraph) + 2 > TARGET_CHARS:
            flush()
        buffer = f"{buffer}\n\n{paragraph}".strip() if buffer else paragraph

    flush()

    # A trailing fragment is folded back rather than stored as its own passage:
    # a two-line chunk retrieves badly and reads as if the answer was cut off.
    if len(chunks) > 1 and len(chunks[-1]) < MIN_CHARS:
        tail = chunks.pop()
        chunks[-1] = f"{chunks[-1]}\n\n{tail}"

    return chunks or ([text.strip()] if text.strip() else [])


def load_document(path: Path) -> Document:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CorpusError(f"{path.name}: invalid JSON ({exc})") from exc

    missing = [f for f in REQUIRED_FIELDS if not raw.get(f)]
    if missing:
        raise CorpusError(
            f"{path.name}: missing required field(s) {', '.join(missing)}. "
            "Every document must record where it came from and under what licence."
        )
    return Document(
        id=raw["id"], title=raw["title"], text=raw["text"], source=raw["source"],
        source_url=raw["source_url"], licence=raw["licence"],
        attribution=raw.get("attribution"),
    )


def iter_documents(corpus_dir: Path = DEFAULT_CORPUS_DIR) -> Iterator[Document]:
    if not corpus_dir.exists():
        return
    for path in sorted(corpus_dir.rglob("*.json")):
        if path.name == "MANIFEST.json":
            continue
        try:
            yield load_document(path)
        except CorpusError as exc:
            # One malformed document must not stop the ingest of the rest.
            logger.warning("Skipping %s", exc)


def passages_from_documents(documents: Sequence[Document]) -> List[Passage]:
    passages: List[Passage] = []
    for document in documents:
        chunks = chunk_text(document.text, document.title)
        multi = len(chunks) > 1
        for index, chunk in enumerate(chunks, start=1):
            # A chunk taken from the middle of a document often opens on a
            # bullet or a dangling clause and never names its subject. Prefixing
            # the title gives the encoder the topic and the reader a stem, and
            # it is what makes chunk 2 of 3 retrievable at all.
            body = chunk if chunk.lstrip().startswith(document.title) else (
                f"{document.title}. {chunk}" if index == 1 else
                f"{document.title} (continued). {chunk}"
            )
            passages.append(
                Passage(
                    id=f"{document.id}#{index}" if multi else document.id,
                    # The part number keeps otherwise-identical titles distinct
                    # in a citation list.
                    title=f"{document.title} ({index}/{len(chunks)})" if multi else document.title,
                    source=f"{document.source} — {document.source_url}",
                    text=body,
                )
            )
    return passages


def load_corpus(corpus_dir: Path = DEFAULT_CORPUS_DIR) -> List[Passage]:
    """The built-in programme guidance plus any fetched reference documents.

    These are different kinds of content and both are needed: the built-in
    passages are programme-specific advice ("stop if you cannot speak in short
    sentences"), while the fetched corpus is general disease reference. Serving
    only the reference material answers "what is angina" well and "how hard
    should I exercise" not at all.
    """
    documents = list(iter_documents(corpus_dir))
    if not documents:
        logger.info(
            "No corpus at %s; using %d built-in passages only. "
            "Run `python -m scripts.fetch_corpus` to add reference documents.",
            corpus_dir, len(BUILTIN_CORPUS),
        )
        return list(BUILTIN_CORPUS)

    fetched = passages_from_documents(documents)
    logger.info(
        "Loaded %d passages from %d fetched documents, plus %d built-in passages",
        len(fetched), len(documents), len(BUILTIN_CORPUS),
    )
    # Built-in first so that on an exact tie the programme's own guidance wins.
    return list(BUILTIN_CORPUS) + fetched
