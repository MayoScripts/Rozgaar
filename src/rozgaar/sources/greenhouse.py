"""Greenhouse public job-board API.

GET https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true
-> {"jobs": [...]}
"""

from __future__ import annotations

from rozgaar.models import Posting
from rozgaar.sources.base import (
    BoardNotFound,
    Source,
    display_name,
    html_to_text,
    parse_iso_date,
)

API = "https://boards-api.greenhouse.io/v1/boards"


class Greenhouse(Source):
    name = "greenhouse"

    def board_title(self, board: str) -> str:
        """The company name the board itself declares ('' if unavailable)."""
        try:
            return str(self._get_json(f"{API}/{board}").get("name") or "").strip()
        except Exception:
            return ""

    def fetch(self, board: str) -> list[Posting]:
        data = self._get_json(f"{API}/{board}/jobs?content=true")
        company = self.board_title(board) or display_name(board)
        return [p for j in data.get("jobs", []) if (p := self._posting(j, board, company))]

    def board_size(self, board: str) -> int:
        try:
            return len(self._get_json(f"{API}/{board}/jobs").get("jobs", []))
        except BoardNotFound:
            return 0

    def _posting(self, j: dict, board: str, company: str) -> Posting | None:
        title = (j.get("title") or "").strip()
        url = (j.get("absolute_url") or "").strip()
        if not title or not url:
            return None
        location = (
            (j.get("location") or {}).get("name", "") if isinstance(j.get("location"), dict) else ""
        )
        if not location:
            offices = j.get("offices") or []
            if offices and isinstance(offices[0], dict):
                location = offices[0].get("name", "")
        return Posting(
            source=self.name,
            board=board,
            company=company,
            title=title,
            url=url,
            location=location.strip(),
            description=html_to_text(j.get("content") or ""),
            # Greenhouse exposes no reliable "published" date; updated_at is
            # the closest signal and is what candidates see as "posted".
            posted_on=parse_iso_date(j.get("updated_at") or j.get("first_published")),
        )
