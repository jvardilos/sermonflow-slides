"""
Provider selection.

One table names every backend, so the CLI and the MCP server never import a
concrete provider, and a new backend is an entry in PROVIDERS rather than a new
branch in each function below. The default is the official ESV API, requiring ESV_API_KEY.
BibleGateway remains available only by explicit provider selection.
"""

from __future__ import annotations

import os
from collections.abc import Callable

from .base import BibleProvider
from .bible_gateway import BibleGatewayProvider
from .esv_api import EsvApiProvider

#: Environment variable holding an api.esv.org application key.
ESV_API_KEY_ENV = "ESV_API_KEY"


def _esv_api() -> BibleProvider:
    """The ESV API backend, keyed from the environment."""
    key = os.environ.get(ESV_API_KEY_ENV)
    if not key:
        raise ValueError(
            f"ESV API setup required: set {ESV_API_KEY_ENV} in the MCP server environment. "
            "Create an application key at https://api.esv.org/. "
            "BibleGateway scraping is no longer an automatic fallback."
        )
    return EsvApiProvider(key)


def _bible_gateway() -> BibleProvider:
    """The BibleGateway scraper, which needs no configuration."""
    return BibleGatewayProvider()


#: Canonical name -> factory. Adding a backend is one entry here.
PROVIDERS: dict[str, Callable[[], BibleProvider]] = {
    "esv-api": _esv_api,
    "bible-gateway": _bible_gateway,
}

#: Other spellings get_provider accepts, each mapped to a key of PROVIDERS.
_ALIASES: dict[str, str] = {
    "esv": "esv-api",
    "esvapi": "esv-api",
    "biblegateway": "bible-gateway",
    "gateway": "bible-gateway",
}


def provider_names() -> list[str]:
    """Canonical backend names, for help text and errors."""
    return list(PROVIDERS)


def get_default_provider() -> BibleProvider:
    """Use the official ESV API; scraping is an explicit CLI opt-in only."""
    return get_provider("esv-api")


def get_provider(name: str) -> BibleProvider:
    """
    A provider by name: a key of PROVIDERS or one of its aliases, in any case.

    "esv-api" reads the key from `ESV_API_KEY` and raises if it is missing.
    """
    normalized = name.strip().lower()
    factory = PROVIDERS.get(_ALIASES.get(normalized, normalized))
    if factory is None:
        choices = " or ".join(repr(known) for known in provider_names())
        raise ValueError(f"unknown provider {name!r}; use {choices}")
    return factory()
