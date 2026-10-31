"""
Verse retrieval, kept behind an interface.

Retrieval is the failure-prone edge of the system: it depends on a third
party's HTML staying put. So it is isolated behind `BibleProvider` (base.py)
and everything durable -- formatting, layout, rendering -- lives above it and
never imports a concrete provider. The one backend is the BibleGateway scraper;
there are no API keys and no other sources.
"""

from __future__ import annotations

from .base import DEFAULT_TRANSLATION, BibleProvider
from .bible_gateway import BibleGatewayProvider, parse_chapter


def get_default_provider() -> BibleProvider:
    """The BibleGateway scraper, which needs no configuration."""
    return BibleGatewayProvider()


__all__ = [
    "DEFAULT_TRANSLATION",
    "BibleProvider",
    "BibleGatewayProvider",
    "get_default_provider",
    "parse_chapter",
]
