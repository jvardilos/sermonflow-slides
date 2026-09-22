"""
Verse retrieval from the official ESV API (api.esv.org).

This is the preferred backend: a first-party, stable, documented JSON API,
free for non-commercial use, and the project is already ESV-first. It needs an
application key, so it activates only when one is present (see registry.py);
without a key the BibleGateway scraper is used instead.

The fetch/parse split mirrors bible_gateway.py: `fetch_chapter` does the HTTP
call, `parse_passage_text` is pure and can be tested offline against a saved
response string. The API returns each verse prefixed with an inline `[n]`
marker (verse numbers on, everything else off), so parsing is a split on those
markers rather than an HTML walk.
"""

from __future__ import annotations

import re
from typing import Any

import requests

from ..text import Verse
from .base import format_citation

API_URL = "https://api.esv.org/v3/passage/text/"

# The API is ESV-only, so the reference label is always ESV regardless of what
# translation code a caller passes for Protocol compatibility.
_TRANSLATION = "ESV"

# An inline verse marker: "[16]" for a single chapter, or "[3:16]" when a
# passage spans chapters. Only the trailing verse number is captured.
_VERSE_MARKER_RE = re.compile(r"\[(?:\d+:)?(\d+)\]")
_WHITESPACE_RE = re.compile(r"\s+")

# Text only, verse numbers on, everything else off -- so the parser sees just
# verses and their [n] markers.
_TEXT_OPTIONS = {
    "include-passage-references": "false",
    "include-verse-numbers": "true",
    "include-first-verse-numbers": "true",
    "include-footnotes": "false",
    "include-headings": "false",
    "include-short-copyright": "false",
    "include-passage-horizontal-lines": "false",
    "include-heading-horizontal-lines": "false",
}


class EsvApiProvider:
    """Fetches chapter text from api.esv.org. Implements BibleProvider."""

    def __init__(self, api_key: str, timeout: int = 15) -> None:
        self.api_key = api_key
        self.timeout = timeout

    def fetch_chapter(
        self, reference: str, translation: str = _TRANSLATION
    ) -> list[Verse]:
        """
        Fetch a chapter and return [(verse_text, reference), ...] in order.

        `translation` is accepted for Protocol compatibility but ignored: the
        ESV API serves only the ESV, so verses are always labelled ESV.

        Raises:
            requests.HTTPError: on a non-2xx response (e.g. a bad API key).
            ValueError: if the response carries no passage text.
        """
        response = requests.get(
            API_URL,
            params={"q": reference, **_TEXT_OPTIONS},
            headers={"Authorization": f"Token {self.api_key}"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        data: Any = response.json()

        passages: list[str] = data.get("passages") or []
        if not passages:
            raise ValueError(f"no passage returned for {reference!r}")
        # canonical is the API's own normalized reference -- "John 3", but
        # "Jude 1-25" for a single-chapter book. Passed through verbatim;
        # format_citation parses it.
        canonical: str = data.get("canonical") or reference
        return parse_passage_text("\n".join(passages), canonical)


def parse_passage_text(passage_text: str, label: str) -> list[Verse]:
    """
    Split ESV passage text on its inline `[n]` verse markers.

    Args:
        passage_text: the API's plain-text passage, verses prefixed with `[n]`.
        label: the source's passage label, e.g. "John 3" or "Jude 1-25".

    Returns [(verse_text, "Book Chapter:Verse ESV"), ...] in verse order.
    Raises ValueError if no verse markers are present.
    """
    markers = list(_VERSE_MARKER_RE.finditer(passage_text))
    if not markers:
        raise ValueError("no verse markers found in passage text")

    verses: list[Verse] = []
    for i, marker in enumerate(markers):
        verse_num = int(marker.group(1))
        start = marker.end()
        end = markers[i + 1].start() if i + 1 < len(markers) else len(passage_text)
        text = _WHITESPACE_RE.sub(" ", passage_text[start:end]).strip()
        if not text:
            continue
        verses.append((text, format_citation(label, verse_num, _TRANSLATION)))
    return verses
