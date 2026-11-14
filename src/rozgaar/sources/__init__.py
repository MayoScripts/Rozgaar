"""Job-board sources. Each one talks to a public, unauthenticated ATS API."""

from __future__ import annotations

import requests

from rozgaar.sources.ashby import Ashby
from rozgaar.sources.base import BoardNotFound, Source, SourceError
from rozgaar.sources.greenhouse import Greenhouse
from rozgaar.sources.lever import Lever

SOURCES: dict[str, type[Source]] = {
    Greenhouse.name: Greenhouse,
    Lever.name: Lever,
    Ashby.name: Ashby,
}


def get_source(name: str, session: requests.Session | None = None) -> Source:
    try:
        return SOURCES[name](session)
    except KeyError:
        raise ValueError(f"unknown source {name!r}; choose from {', '.join(SOURCES)}") from None


__all__ = ["SOURCES", "BoardNotFound", "Source", "SourceError", "get_source"]
