"""Fetch the cardiovascular subset of the MedlinePlus health-topic feed.

MedlinePlus mixes public-domain and licensed content. The health-topic XML feed
is the public-domain subset produced by the National Library of Medicine; the
A.D.A.M. Medical Encyclopedia articles and the ASHP drug monographs on the same
site are licensed third-party material and are deliberately NOT touched here.

    Reuse terms: https://medlineplus.gov/about/using/usingcontent/
    Feed:        https://medlineplus.gov/xml.html

Every document written carries its source URL, licence and retrieval date, so
provenance travels with the text rather than living in someone's memory.

Usage:
    python -m scripts.fetch_corpus                # default output: ./corpus
    python -m scripts.fetch_corpus --out ./corpus --max-topics 200
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
import urllib.error
import urllib.request
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator, List, Optional
from xml.etree import ElementTree

BASE_URL = "https://medlineplus.gov/xml"
FILE_TEMPLATE = "mplus_topics_compressed_{date}.zip"
USER_AGENT = "cardiac-rehab-platform/1.0 (portfolio project; contact via repository)"

LICENCE = "Public domain (work of the U.S. National Library of Medicine)"
ATTRIBUTION = "Courtesy of MedlinePlus from the National Library of Medicine"

# Topic groups worth keeping for a cardiac rehabilitation programme.
WANTED_GROUPS = {
    "heart and circulation",
    "blood, heart and circulation",
    "blood, heart, and circulation",
}

# Topics outside those groups that a rehab patient still asks about.
WANTED_TITLES = {
    "exercise and physical fitness", "physical activity", "smoking",
    "quitting smoking", "nutrition", "dietary fats", "sodium",
    "weight control", "obesity", "diabetes", "stress", "anxiety",
    "depression", "sleep disorders", "alcohol", "cholesterol",
    "blood pressure medicines", "blood thinners", "statins",
    "cardiac rehabilitation", "heart health tests",
}

# Titles to drop even when their group matches: paediatric and rare-disease
# topics are noise for an adult rehabilitation programme.
EXCLUDED_PATTERNS = [
    # Paediatric and congenital: wrong cohort for adult phase-II rehab.
    r"\bin children\b", r"\bchildhood\b", r"\bcongenital\b", r"\bpediatric\b",
    r"\bin infants\b", r"\bnewborn\b",
    # The "Blood, Heart and Circulation" group also covers haematology and blood
    # cancers. Retrieving a leukemia page for a cardiac rehab question is not
    # merely irrelevant — it is alarming to the patient reading it.
    r"\bleukemia\b", r"\blymphoma\b", r"\bmyeloma\b", r"\bcancer\b",
    r"\btumor\b", r"\btumour\b",
    r"\bhemophilia\b", r"\bhaemophilia\b", r"\bsickle cell\b",
    r"\bthalassemia\b", r"\bvon willebrand\b", r"\bbone marrow\b",
    r"\bplatelet disorders\b", r"\bbleeding disorders\b",
    r"\bblood transfusion\b", r"\bblood donation\b", r"\bblood count\b",
    r"\bporphyria\b", r"\bhemochromatosis\b", r"\bhaemochromatosis\b",
]

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t\r\f\v]+")
_BLANKS_RE = re.compile(r"\n{3,}")


def latest_feed_url(max_lookback_days: int = 10) -> tuple[str, date]:
    """The feed is published under a dated filename, so walk back from today.

    Publication skips Sundays and Mondays, and a same-day file may not exist
    yet, so a short lookback is normal rather than an error condition.
    """
    today = datetime.now(timezone.utc).date()
    for offset in range(max_lookback_days):
        day = today - timedelta(days=offset)
        url = f"{BASE_URL}/{FILE_TEMPLATE.format(date=day.isoformat())}"
        request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                if response.status == 200:
                    return url, day
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise
        except urllib.error.URLError:
            raise
    raise SystemExit(
        f"No feed found in the last {max_lookback_days} days. Check {BASE_URL}.html "
        "for the current file name."
    )


def download(url: str) -> bytes:
    print(f"Downloading {url}")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=300) as response:
        data = response.read()
    print(f"  {len(data) / 1_048_576:.1f} MB")
    return data


def clean(html: str) -> str:
    """Strip markup and normalise whitespace, keeping paragraph breaks."""
    text = html.replace("</p>", "\n\n").replace("<br />", "\n").replace("<br/>", "\n")
    text = text.replace("</li>", "\n").replace("<li>", "- ")
    text = _TAG_RE.sub("", text)
    for entity, char in (
        ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'),
        ("&#39;", "'"), ("&nbsp;", " "), ("&rsquo;", "'"), ("&ldquo;", '"'),
        ("&rdquo;", '"'), ("&mdash;", "—"), ("&ndash;", "–"),
    ):
        text = text.replace(entity, char)
    text = _WS_RE.sub(" ", text)
    text = _BLANKS_RE.sub("\n\n", text)

    # Unwrap hard line breaks inside a paragraph. The feed wraps mid-sentence,
    # and leaving those breaks in would split sentences across chunks later.
    paragraphs = []
    for block in text.split("\n\n"):
        lines = [line.strip() for line in block.split("\n") if line.strip()]
        if not lines:
            continue
        merged: List[str] = []
        for line in lines:
            # A list item starts its own line; prose continues the previous one.
            if line.startswith("- ") or not merged:
                merged.append(line)
            else:
                merged[-1] = f"{merged[-1]} {line}"
        paragraphs.append("\n".join(merged))
    return "\n\n".join(paragraphs).strip()


def is_excluded(title: str) -> bool:
    lowered = title.lower()
    return any(re.search(p, lowered) for p in EXCLUDED_PATTERNS)


def wanted(title: str, groups: List[str]) -> bool:
    if is_excluded(title):
        return False
    if any(g.lower() in WANTED_GROUPS for g in groups):
        return True
    return title.lower() in WANTED_TITLES


def iter_topics(xml_bytes: bytes) -> Iterator[dict]:
    """Stream the feed rather than building a full tree: the uncompressed XML is
    ~29 MB and only a fraction of it is kept."""
    context = ElementTree.iterparse(io.BytesIO(xml_bytes), events=("end",))
    for _, element in context:
        if element.tag != "health-topic":
            continue
        if element.get("language") != "English":
            element.clear()
            continue

        title = (element.get("title") or "").strip()
        url = (element.get("url") or "").strip()
        summary_el = element.find("full-summary")
        groups = [g.text.strip() for g in element.findall("group") if g.text]
        also_called = [a.text.strip() for a in element.findall("also-called") if a.text]

        if title and summary_el is not None and summary_el.text:
            yield {
                "title": title,
                "url": url,
                "groups": groups,
                "also_called": also_called,
                "summary": summary_el.text,
            }
        element.clear()


def slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug[:80] or "topic"


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("corpus") / "medlineplus")
    parser.add_argument("--max-topics", type=int, default=0, help="0 means no limit")
    parser.add_argument("--min-chars", type=int, default=300,
                        help="Skip stub topics shorter than this.")
    args = parser.parse_args(argv)

    url, published = latest_feed_url()
    archive = download(url)

    with zipfile.ZipFile(io.BytesIO(archive)) as zf:
        name = next(n for n in zf.namelist() if n.endswith(".xml"))
        print(f"  reading {name}")
        xml_bytes = zf.read(name)

    args.out.mkdir(parents=True, exist_ok=True)
    retrieved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    kept: List[dict] = []
    seen_slugs: set[str] = set()
    scanned = 0

    for topic in iter_topics(xml_bytes):
        scanned += 1
        if not wanted(topic["title"], topic["groups"]):
            continue

        text = clean(topic["summary"])
        if len(text) < args.min_chars:
            continue

        slug = slugify(topic["title"])
        if slug in seen_slugs:
            continue
        seen_slugs.add(slug)

        document = {
            "id": f"medlineplus/{slug}",
            "title": topic["title"],
            "text": text,
            "also_called": topic["also_called"],
            "groups": topic["groups"],
            # Provenance travels with the document.
            "source": "MedlinePlus (U.S. National Library of Medicine)",
            "source_url": topic["url"],
            "licence": LICENCE,
            "attribution": ATTRIBUTION,
            "retrieved_at": retrieved_at,
            "feed_published": published.isoformat(),
        }
        (args.out / f"{slug}.json").write_text(
            json.dumps(document, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        kept.append({"id": document["id"], "title": document["title"], "chars": len(text)})

        if args.max_topics and len(kept) >= args.max_topics:
            break

    manifest = {
        "source": "MedlinePlus health topics",
        "feed_url": url,
        "feed_published": published.isoformat(),
        "retrieved_at": retrieved_at,
        "licence": LICENCE,
        "attribution": ATTRIBUTION,
        "excluded": "A.D.A.M. Medical Encyclopedia and ASHP drug monographs are "
                    "licensed third-party content and are not included.",
        "topics_scanned": scanned,
        "documents": sorted(kept, key=lambda d: d["title"]),
    }
    (args.out.parent / "MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    total_chars = sum(d["chars"] for d in kept)
    print(f"\nScanned {scanned} English topics")
    print(f"Kept    {len(kept)} documents  ({total_chars:,} characters)")
    print(f"Written to {args.out}")
    print(f"Manifest at {args.out.parent / 'MANIFEST.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
