"""
Provider selection.

One table names every backend, so the CLI and the MCP server never import a
concrete provider, and a new backend is an entry in PROVIDERS rather than a new
branch in each function below. The default is zero-config: the ESV API when an
`ESV_API_KEY` is in the environment, otherwise the BibleGateway scraper so the
tool still runs with nothing set up.
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
            f"the esv-api provider needs {ESV_API_KEY_ENV} in the environment"
        )
    return EsvApiProvider(key)


#: Canonical name -> factory. Adding a backend is one entry here.
PROVIDERS: dict[str, Callable[[], BibleProvider]] = {
    "esv-api": _esv_api,
    "bible-gateway": BibleGatewayProvider,
}

#: Other spellings get_provider accepts, each mapped to a key of PROVIDERS.
_ALIASES: dict[str, str] = {
    "esv": "esv-api",
    "esvapi": "esv-api",
    "biblegateway": "bible-gateway",
    "gateway": "bible-gateway",
}


def get_default_provider() -> BibleProvider:
    """ESV API if `ESV_API_KEY` is set, else the BibleGateway scraper."""
    return get_provider("esv-api" if os.environ.get(ESV_API_KEY_ENV) else "bible-gateway")


def get_provider(name: str) -> BibleProvider:
    """
    A provider by name: a key of PROVIDERS or one of its aliases, in any case.

    "esv-api" reads the key from `ESV_API_KEY` and raises if it is missing.
    """
    normalized = name.strip().lower()
    factory = PROVIDERS.get(_ALIASES.get(normalized, normalized))
    if factory is None:
        choices = " or ".join(repr(known) for known in PROVIDERS)
        raise ValueError(f"unknown provider {name!r}; use {choices}")
    return factory()
