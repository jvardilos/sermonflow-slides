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
_JUNK_CLASSES = ("footnote", "crossreference", "versenum", "chapternum")

# Selectors are written against class names only, never element names: the
# page has swapped <div> for <span> (and could again) without changing classes.
_HEADING_SELECTORS = (
    ".bcv .dropdown-display-text",
    ".bcv",
    ".passage-display .dropdown-display-text",
)
_SECTION_HEADINGS = ("h1", "h2", "h3", "h4", "h5", "h6")


def _verse_match(tag) -> re.Match[str] | None:
    """The Book-Chapter-Verse class match on `tag`, whatever its element is."""
    classes = cast("list[str]", tag.get("class") or [])
    return next(
        (m for m in (_VERSE_CLASS_RE.match(c) for c in classes) if m),
        None,
    )


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

    heading = next(
        (h for sel in _HEADING_SELECTORS if (h := soup.select_one(sel))), None
    )
    if heading is None:
        raise ValueError("no passage found on page")
    # Passed through verbatim: format_citation parses it. The heading is
    # "John 17" for most books but a bare "Jude" for the single-chapter
    # ones, and normalizing that difference is not this module's job.
    label = heading.get_text(strip=True)

    body = soup.select_one(
        f".passage-content .version-{translation}"
    ) or soup.select_one(f".version-{translation}")
    if body is None:
        raise ValueError(f"no {translation} text found on page")

    fragments: dict[int, list[str]] = {}
    order: list[int] = []
    for span in body.find_all(lambda t: _verse_match(t) is not None):
        if span.find_parent(_SECTION_HEADINGS):
            continue  # section heading
        if any(_verse_match(p) for p in span.parents):
            continue  # inside a verse element already taken
        match = _verse_match(span)
        assert match is not None
        verse_num = int(match.group(3))

        for junk in span.find_all(class_=_JUNK_CLASSES):
            junk.decompose()
        # The divine name (LORD, GOD) is small capitals in print, which the page
        # does with CSS over the text "Lord". Keeping only the text would turn
        # YHWH into Adonai, so the capitals are made literal here.
        for name in span.find_all(class_="small-caps"):
            name.replace_with(name.get_text().upper())

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
