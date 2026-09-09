"""
Verse retrieval, kept behind an interface.

Retrieval is the failure-prone edge of the system: it depends on a third
party's HTML or API staying put. So it is isolated behind `BibleProvider`
(base.py) and everything durable -- formatting, layout, rendering -- lives
above it and never imports a concrete provider. Swap the backend by adding a
class here and pointing the registry at it; nothing downstream changes.
"""

from __future__ import annotations

from .base import DEFAULT_TRANSLATION, BibleProvider
from .bible_gateway import BibleGatewayProvider, parse_chapter
from .esv_api import EsvApiProvider, parse_passage_text
from .registry import get_default_provider, get_provider

__all__ = [
    "DEFAULT_TRANSLATION",
    "BibleProvider",
    "BibleGatewayProvider",
    "EsvApiProvider",
    "get_default_provider",
    "get_provider",
    "parse_chapter",
    "parse_passage_text",
]
