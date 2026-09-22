"""
The retrieval contract every backend must honour.

A provider does exactly one thing: given a human reference and a translation
code, return the chapter's verses as (verse_text, reference) pairs in verse
order, where the reference is "Book Chapter:Verse TRANSLATION". Everything
above this line -- formatting, layout, rendering -- depends only on that shape,
never on how the text was obtained.
"""

from __future__ import annotations

import re
from typing import Protocol, runtime_checkable

from ..text import Verse

#: Default translation code. ESV is the deck's translation and the ESV API's
#: only offering, so it is the project default.
DEFAULT_TRANSLATION = "ESV"

#: Hyphen plus the Unicode dashes a source might write a range with -- the ESV
#: API uses an en dash, BibleGateway a plain hyphen.
_DASHES = r"-‐-―"

#: A passage label as a source states it, e.g. "John 17", "1 John 4", "Jude",
#: "Jude 1-25". The book may carry a leading numeral ("3 John") and may be
#: several words ("Song of Solomon"); the chapter, when there is one, is the
#: trailing number, optionally written as a range.
_LABEL_RE = re.compile(
    rf"""^\s*
        (?P<book>(?:[1-3]\s+)?[A-Za-z][A-Za-z\s]*?)
        (?:\s+(?P<chapter>\d+)(?P<range>\s*[{_DASHES}]\s*\d+)?)?
        \s*$""",
    re.VERBOSE,
)


def split_label(label: str) -> tuple[str, int]:
    """
    Split a source's passage label into (book, chapter).

    Backends label verses from whatever the source calls the passage, and the
    sources disagree. BibleGateway's heading for Jude is "Jude"; the ESV API
    normalizes the same request to something like "Jude 1-25". Pasting
    ":verse" onto either produced "Jude:1 ESV" and "Jude 1-25:3 ESV" on screen
    -- so the label is parsed here rather than trusted, and every backend lands
    on the same citation.

    A trailing *range* rather than a single number means the source expanded a
    whole book into its verse range, which only happens for the single-chapter
    books (Jude, Philemon, Obadiah, 2 and 3 John). Since fetch_chapter's
    contract is one chapter, that range is verses, not chapters, and the
    chapter is 1. A label with no number at all is the same case stated
    differently. Anything unparseable keeps the label as the book and
    chapter 1 -- wrong on a screen, but never a crash mid-service.
    """
    head = label.split(":")[0].strip()
    match = _LABEL_RE.match(head)
    if match is None:
        return head, 1
    book = " ".join(match.group("book").split())
    chapter = match.group("chapter")
    if chapter is None or match.group("range"):
        return book, 1
    return book, int(chapter)


def format_citation(
    label: str, verse: int, translation: str = DEFAULT_TRANSLATION
) -> str:
    """
    The reference line for one verse: "John 17:1 ESV", "Jude 1:3 ESV".

    Always "Book Chapter:Verse TRANSLATION" -- the shape this module's contract
    promises and the rest of the pipeline (not least the slide filename) reads
    back out. Single-chapter books get an explicit chapter 1 rather than the
    verse-only form a scholar would write: the redundant "1:" is the convention
    on screen, and it keeps every slide in a deck labelled the same way.
    """
    book, chapter = split_label(label)
    return f"{book} {chapter}:{verse} {translation}"


@runtime_checkable
class BibleProvider(Protocol):
    """A source of chapter text. See module docstring for the contract."""

    def fetch_chapter(
        self, reference: str, translation: str = DEFAULT_TRANSLATION
    ) -> list[Verse]:
        """
        Return [(verse_text, "Book Chapter:Verse TRANSLATION"), ...] in order.

        Raises:
            ValueError: if the reference resolves to no passage.
            requests.HTTPError: on a non-2xx response from a networked backend.
        """
        ...
