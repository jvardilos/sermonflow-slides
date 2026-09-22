"""
Provider selection.

One place decides which backend to use, so the CLI and the MCP server never
import a concrete provider. The rule is simple and zero-config: use the ESV API
when an `ESV_API_KEY` is in the environment, otherwise fall back to the
BibleGateway scraper so the tool still runs with nothing set up.
"""

from __future__ import annotations

import os

from .base import BibleProvider

#: Environment variable holding an api.esv.org application key.
ESV_API_KEY_ENV = "ESV_API_KEY"


def get_default_provider() -> BibleProvider:
    """
    The provider chosen from the environment.

    ESV API if `ESV_API_KEY` is set, else the BibleGateway scraper.
    """
    key = os.environ.get(ESV_API_KEY_ENV)
    if key:
        from .esv_api import EsvApiProvider

        return EsvApiProvider(key)

    from .bible_gateway import BibleGatewayProvider

    return BibleGatewayProvider()


def get_provider(name: str) -> BibleProvider:
    """
    A provider by explicit name: "esv-api" or "bible-gateway".

    "esv-api" reads the key from `ESV_API_KEY` and raises if it is missing.
    """
    normalized = name.strip().lower()
    if normalized in ("esv", "esv-api", "esvapi"):
        from .esv_api import EsvApiProvider

        key = os.environ.get(ESV_API_KEY_ENV)
        if not key:
            raise ValueError(
                f"the esv-api provider needs {ESV_API_KEY_ENV} in the environment"
            )
        return EsvApiProvider(key)
    if normalized in ("bible-gateway", "biblegateway", "gateway"):
        from .bible_gateway import BibleGatewayProvider

        return BibleGatewayProvider()
    raise ValueError(f"unknown provider {name!r}; use 'esv-api' or 'bible-gateway'")
