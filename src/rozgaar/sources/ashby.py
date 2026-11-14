"""Ashby public job-board API.

GET https://api.ashbyhq.com/posting-api/job-board/{board}?includeCompensation=true
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

API = "https://api.ashbyhq.com/posting-api/job-board"


class Ashby(Source):
    name = "ashby"

    def fetch(self, board: str) -> list[Posting]:
        data = self._get_json(f"{API}/{board}?includeCompensation=true")
        company = display_name(board)
        return [p for j in data.get("jobs") or [] if (p := self._posting(j, board, company))]

    def board_size(self, board: str) -> int:
        try:
            return len(self._get_json(f"{API}/{board}").get("jobs") or [])
        except BoardNotFound:
            return 0

    def _posting(self, j: dict, board: str, company: str) -> Posting | None:
        if j.get("isListed") is False:
            return None
        title = (j.get("title") or "").strip()
        url = (j.get("jobUrl") or j.get("applyUrl") or "").strip()
        if not title or not url:
            return None
        location = (j.get("location") or j.get("locationName") or "").strip()
        if j.get("isRemote") and "remote" not in location.lower():
            location = f"{location} (Remote)".strip() if location else "Remote"
        comp = j.get("compensation")
        salary = (comp.get("compensationTierSummary") or "") if isinstance(comp, dict) else ""
        return Posting(
            source=self.name,
            board=board,
            company=company,
            title=title,
            url=url,
            location=location,
            description=j.get("descriptionPlain") or html_to_text(j.get("descriptionHtml") or ""),
            salary_text=str(salary)[:160],
            posted_on=parse_iso_date(j.get("publishedAt") or j.get("updatedAt")),
        )
