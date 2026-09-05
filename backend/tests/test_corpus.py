"""Corpus loading, provenance enforcement and chunking."""
import json

import pytest

from app.services.corpus import (
    MAX_CHARS, CorpusError, chunk_text, load_corpus, load_document,
    passages_from_documents,
)

VALID = {
    "id": "medlineplus/heart-attack",
    "title": "Heart Attack",
    "text": "A heart attack happens when blood flow to the heart is blocked.",
    "source": "MedlinePlus (U.S. National Library of Medicine)",
    "source_url": "https://medlineplus.gov/heartattack.html",
    "licence": "Public domain",
    "attribution": "Courtesy of MedlinePlus",
}


def write(tmp_path, name, payload):
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_valid_document_loads(tmp_path):
    doc = load_document(write(tmp_path, "a.json", VALID))
    assert doc.title == "Heart Attack"
    assert doc.source_url.startswith("https://")


@pytest.mark.parametrize("field", ["source_url", "licence", "source", "title", "text"])
def test_document_without_provenance_is_refused(tmp_path, field):
    """Unattributed text must never reach a patient-facing answer."""
    payload = {**VALID, field: ""}
    with pytest.raises(CorpusError) as exc:
        load_document(write(tmp_path, "bad.json", payload))
    assert field in str(exc.value)


def test_invalid_json_is_refused(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(CorpusError):
        load_document(path)


def test_one_bad_document_does_not_stop_the_rest(tmp_path, caplog):
    write(tmp_path, "good.json", VALID)
    write(tmp_path, "bad.json", {**VALID, "id": "x/bad", "title": "Bad Doc", "licence": ""})
    titles = [p.title for p in load_corpus(tmp_path)]
    assert "Heart Attack" in titles
    assert "Bad Doc" not in titles


def test_falls_back_to_builtin_passages_when_no_corpus(tmp_path):
    passages = load_corpus(tmp_path / "does-not-exist")
    assert len(passages) > 10
    assert any("exercise" in p.title.lower() for p in passages)


def test_short_document_is_a_single_chunk():
    assert len(chunk_text("One short paragraph about recovery.", "T")) == 1


def test_paragraphs_are_packed_not_split_arbitrarily():
    text = "\n\n".join(f"Paragraph {i}. " + "word " * 40 for i in range(6))
    chunks = chunk_text(text, "T")
    assert len(chunks) > 1
    assert all(len(c) <= MAX_CHARS + 200 for c in chunks)
    # No chunk starts mid-sentence.
    assert all(c[0].isupper() or c[0].isdigit() or c.startswith("-") for c in chunks)


def test_oversized_paragraph_is_split_on_sentences_with_overlap():
    sentence = "This is a sentence about cardiac rehabilitation exercise. "
    chunks = chunk_text(sentence * 60, "T")
    assert len(chunks) > 1
    # One sentence of overlap means consecutive chunks share text.
    first_tail = chunks[0].split(". ")[-2]
    assert first_tail in chunks[1]


def test_tiny_trailing_fragment_is_folded_back():
    text = "\n\n".join(["A. " + "word " * 60, "B. " + "word " * 60, "Tiny tail."])
    chunks = chunk_text(text, "T")
    assert "Tiny tail." in chunks[-1]
    assert len(chunks[-1]) > 100


def test_chunked_document_produces_numbered_passages(tmp_path):
    long_doc = {**VALID, "text": "\n\n".join(f"Para {i}. " + "word " * 60 for i in range(8))}
    write(tmp_path, "long.json", long_doc)
    chunks = [p for p in load_corpus(tmp_path) if p.id.startswith("medlineplus/heart-attack")]
    assert len(chunks) > 1
    assert chunks[0].id.endswith("#1")
    assert "(1/" in chunks[0].title
    # Provenance survives chunking.
    assert "medlineplus.gov" in chunks[0].source
    # Every chunk names its subject, so chunk 2 is retrievable on its own.
    assert all("Heart Attack" in c.text for c in chunks)


def test_single_chunk_document_keeps_a_clean_id_and_title(tmp_path):
    write(tmp_path, "a.json", VALID)
    passage = next(p for p in load_corpus(tmp_path) if p.id.startswith("medlineplus/"))
    assert passage.id == "medlineplus/heart-attack"
    assert passage.title == "Heart Attack"


def test_builtin_guidance_is_merged_with_fetched_documents(tmp_path):
    """Regression: fetching a reference corpus once silently replaced the
    programme's own guidance, so 'how hard should I exercise' had no answer."""
    write(tmp_path, "a.json", VALID)
    titles = [p.title for p in load_corpus(tmp_path)]

    assert "Heart Attack" in titles                      # fetched
    assert "How hard should I exercise?" in titles       # built-in
    assert len(titles) > 20


def test_builtin_passages_come_first(tmp_path):
    """On an equal score the programme's own advice should win over general
    reference material."""
    write(tmp_path, "a.json", VALID)
    passages = load_corpus(tmp_path)
    assert passages[0].source.startswith("Programme handbook")
