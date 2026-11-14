"""Lever public postings API.

GET https://api.lever.co/v0/postings/{board}?mode=json -> [...]
"""

from __future__ import annotations

from rozgaar.models import Posting
from rozgaar.sources.base import (
    BoardNotFound,
    Source,
    SourceError,
    display_name,
    html_to_text,
    parse_epoch_ms,
)

API = "https://api.lever.co/v0/postings"


def _salary(p: dict) -> str:
    sal = p.get("salaryRange")
    if not isinstance(sal, dict) or not sal.get("min") or not sal.get("max"):
        return ""
    try:
        lo, hi = int(sal["min"]), int(sal["max"])
    except (TypeError, ValueError):
        return ""
    return f"{sal.get('currency', 'USD')} {lo:,}–{hi:,}"


class Lever(Source):
    name = "lever"

    def _postings(self, board: str) -> list[dict]:
        data = self._get_json(f"{API}/{board}?mode=json")
        if not isinstance(data, list):
            raise SourceError(f"lever: unexpected response shape for {board}")
        return data

    def fetch(self, board: str) -> list[Posting]:
        company = display_name(board)
        return [p for raw in self._postings(board) if (p := self._posting(raw, board, company))]

    def board_size(self, board: str) -> int:
        try:
            return len(self._postings(board))
        except (BoardNotFound, SourceError):
            return 0

    def _posting(self, p: dict, board: str, company: str) -> Posting | None:
        title = (p.get("text") or "").strip()
        # applyUrl lands on the form; hostedUrl is the public listing.
        url = (p.get("hostedUrl") or p.get("applyUrl") or "").strip()
        if not title or not url:
            return None
        cats = p.get("categories") or {}
        location = (cats.get("location") or "").strip()
        if not location and isinstance(cats.get("allLocations"), list) and cats["allLocations"]:
            location = str(cats["allLocations"][0])
        description = p.get("descriptionPlain") or html_to_text(p.get("description") or "")
        # Requirements usually live in `lists` ("What you'll need", ...).
        for block in p.get("lists") or []:
            if isinstance(block, dict):
                description += (
                    "\n"
                    + (block.get("text") or "")
                    + "\n"
                    + html_to_text(block.get("content") or "")
                )
        return Posting(
            source=self.name,
            board=board,
            company=company,
            title=title,
            url=url,
            location=location,
            description=description.strip(),
            salary_text=_salary(p),
            posted_on=parse_epoch_ms(p.get("createdAt")),
        )
