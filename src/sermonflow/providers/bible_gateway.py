"""
Verse retrieval from BibleGateway by scraping the passage page.

This is the zero-configuration fallback: it needs no API key, so the tool runs
out of the box. It is also the fragile one -- it parses HTML, so it will break
whenever BibleGateway restyles their passage page. That is exactly why
retrieval is behind `BibleProvider`: prefer the ESV API (esv_api.py) when a key
is available, and keep this as the always-there backup.

It does as little as possible: fetch, pull the verse spans out, hand back *raw*
verse strings. All display formatting lives in sermonflow.text so it survives
this module being replaced. The only cleanup done here is structural -- dropping
footnote/cross-reference/verse-number nodes, which is far more reliable against
the DOM than against a flat string. sermonflow.text.find_artifacts is the regex
safety net for anything that slips through.
"""

from __future__ import annotations

import re
from typing import cast

import requests
from bs4 import BeautifulSoup

from ..text import Verse
from .base import DEFAULT_TRANSLATION, format_citation

PASSAGE_URL = "https://www.biblegateway.com/passage/"

# Verse-identifying class on each text span, e.g. "John-17-6" or "1John-4-18".
_VERSE_CLASS_RE = re.compile(r"^([1-3]?[A-Za-z]+)-(\d+)-(\d+)$")
_WHITESPACE_RE = re.compile(r"\s+")

# Nodes that are navigation aids, not scripture.
_JUNK_SUP_CLASSES = ("footnote", "crossreference", "versenum")


class BibleGatewayProvider:
    """Scrapes BibleGateway's passage page. Implements BibleProvider."""

    def __init__(self, timeout: int = 15) -> None:
        self.timeout = timeout

    def fetch_chapter(
        self, reference: str, translation: str = DEFAULT_TRANSLATION
    ) -> list[Verse]:
        """
        Fetch a chapter and return [(verse_text, reference), ...] in order.

        Args:
            reference: book and chapter, e.g. "John 17" or "1 John 4". Passed
                through to BibleGateway's own search, so anything it resolves
                works here.
            translation: version code, ESV by default.

        Raises:
            requests.HTTPError: on a non-2xx response.
            ValueError: if the page contains no passage for this reference.
        """
        response = requests.get(
            PASSAGE_URL,
            params={"search": reference, "version": translation},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return parse_chapter(response.text, translation)


def parse_chapter(html: str, translation: str = DEFAULT_TRANSLATION) -> list[Verse]:
    """
    Pull verses out of a BibleGateway passage page.

    Split out from the provider so it can be exercised against a saved page
    without touching the network.
    """
    soup = BeautifulSoup(html, "html.parser")

    heading = soup.select_one("div.bcv .dropdown-display-text")
    if heading is None:
        raise ValueError("no passage found on page")
    # Passed through verbatim: format_citation parses it. The heading is
    # "John 17" for most books but a bare "Jude" for the single-chapter
    # ones, and normalizing that difference is not this module's job.
    label = heading.get_text(strip=True)

    body = soup.select_one(f"div.passage-content div.version-{translation}")
    if body is None:
        raise ValueError(f"no {translation} text found on page")

    fragments: dict[int, list[str]] = {}
    order: list[int] = []
    for span in body.find_all("span", class_="text"):
        if span.find_parent("h3"):
            continue  # section heading

        classes = cast("list[str]", span.get("class") or [])
        match = next(
            (m for m in (_VERSE_CLASS_RE.match(c) for c in classes) if m),
            None,
        )
        if match is None:
            continue
        verse_num = int(match.group(3))

        for junk in span.find_all("sup", class_=_JUNK_SUP_CLASSES):
            junk.decompose()
        for junk in span.find_all("span", class_="chapternum"):
            junk.decompose()

        text = _WHITESPACE_RE.sub(" ", span.get_text()).strip()
        if not text:
            continue

        if verse_num not in fragments:
            fragments[verse_num] = []
            order.append(verse_num)
        fragments[verse_num].append(text)

    if not order:
        raise ValueError("passage contained no verses")

    return [
        (
            _WHITESPACE_RE.sub(" ", " ".join(fragments[n])).strip(),
            format_citation(label, n, translation),
        )
        for n in order
    ]
