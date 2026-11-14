"""Plain data types passed between pipeline stages."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date


@dataclass
class Posting:
    """One job posting as fetched from a board, normalised across ATS types."""

    source: str  # "greenhouse" | "lever" | "ashby"
    board: str  # the board slug it came from
    company: str
    title: str
    url: str  # direct link to the posting / application
    location: str = ""
    description: str = ""  # plain text
    salary_text: str = ""
    posted_on: date | None = None

    @property
    def id(self) -> str:
        """Stable id derived from the URL."""
        return hashlib.sha1(self.url.encode("utf-8")).hexdigest()[:16]

    def age_days(self, today: date | None = None) -> int | None:
        if self.posted_on is None:
            return None
        return max(0, ((today or date.today()) - self.posted_on).days)


@dataclass
class ParsedJD:
    """Structured facts pulled out of a job description."""

    must_have: list[str] = field(default_factory=list)
    nice_to_have: list[str] = field(default_factory=list)
    min_years: int | None = None
    seniority: str = "unknown"  # entry | mid | senior | lead+ | unknown
    role_family: str = "other"
    domain: str | None = None
    work_mode: str = "unclear"  # remote | hybrid | onsite | unclear
    salary_min: int | None = None
    salary_max: int | None = None
    parser: str = ""  # which parser produced this

    def to_dict(self) -> dict:
        return dict(self.__dict__)

    @classmethod
    def from_dict(cls, d: dict) -> ParsedJD:
        known = {k: d[k] for k in cls.__dataclass_fields__ if k in d}
        return cls(**known)


@dataclass
class Fit:
    """How well a posting matches the profile."""

    grade: str | None  # "A" | "B" | "C" | None (could not grade)
    score: float | None
    covered: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    reason: str = ""

    def to_dict(self) -> dict:
        return dict(self.__dict__)
