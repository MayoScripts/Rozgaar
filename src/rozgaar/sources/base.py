"""Shared plumbing for board sources."""

from __future__ import annotations

import html
import logging
import re
from abc import ABC, abstractmethod
from datetime import date, datetime, timezone

import requests

from rozgaar import __version__
from rozgaar.models import Posting

log = logging.getLogger(__name__)

USER_AGENT = f"rozgaar/{__version__} (+https://github.com/MayoScripts/rozgaar)"
TIMEOUT_S = 15
MAX_DESCRIPTION_CHARS = 8000


class BoardNotFound(LookupError):
    """The board slug does not exist on this ATS."""


class SourceError(RuntimeError):
    """The board could not be fetched (network error, bad response)."""


def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})
    return s


_TAG = re.compile(r"<[^>]+>")
_BLOCK = re.compile(r"</?(p|div|li|ul|ol|br|h[1-6]|tr)\b[^>]*>", re.IGNORECASE)
_SPACE = re.compile(r"[ \t\f\v]+")


def html_to_text(raw: str) -> str:
    """Strip HTML to readable plain text, keeping paragraph breaks.

    Some APIs (Greenhouse) return entity-escaped HTML, so unescape first,
    then drop tags, then unescape again for entities that were inside tags'
    text content.
    """
    if not raw:
        return ""
    text = html.unescape(raw)
    text = _BLOCK.sub("\n", text)
    text = html.unescape(_TAG.sub(" ", text))
    lines = (_SPACE.sub(" ", line).strip() for line in text.splitlines())
    text = "\n".join(line for line in lines if line)
    return text[:MAX_DESCRIPTION_CHARS]


def parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def parse_epoch_ms(value: int | str | None) -> date | None:
    if value in (None, ""):
        return None
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc).date()
    except (TypeError, ValueError, OSError):
        return None


def display_name(slug: str) -> str:
    """Fallback company name from a board slug: 'monte-carlo' -> 'Monte Carlo'."""
    return re.sub(r"[-_]+", " ", slug).strip().title()


class Source(ABC):
    """A job-board API. Subclasses turn one board slug into postings."""

    name: str = ""

    def __init__(self, session: requests.Session | None = None) -> None:
        self.session = session or make_session()

    def _get_json(self, url: str):
        try:
            resp = self.session.get(url, timeout=TIMEOUT_S)
        except requests.RequestException as e:
            raise SourceError(f"{self.name}: {e}") from e
        if resp.status_code == 404:
            raise BoardNotFound(url)
        if resp.status_code != 200:
            raise SourceError(f"{self.name}: HTTP {resp.status_code} for {url}")
        try:
            return resp.json()
        except ValueError as e:
            raise SourceError(f"{self.name}: response was not JSON") from e

    @abstractmethod
    def fetch(self, board: str) -> list[Posting]:
        """Return every open posting on ``board``.

        Raises :class:`BoardNotFound` if the slug doesn't exist and
        :class:`SourceError` on any other failure.
        """

    @abstractmethod
    def board_size(self, board: str) -> int:
        """Number of open postings on ``board``; 0 if it doesn't exist.
        Used by board discovery, so it should be cheap."""
