"""
The retrieval contract every backend must honour.

A provider does exactly one thing: given a human reference and a translation
code, return the chapter's verses as (verse_text, reference) pairs in verse
order, where the reference is "Book Chapter:Verse TRANSLATION". Everything
above this line -- formatting, layout, rendering -- depends only on that shape,
never on how the text was obtained.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..text import Verse

#: Default translation code. ESV is the deck's translation and the ESV API's
#: only offering, so it is the project default.
DEFAULT_TRANSLATION = "ESV"


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
