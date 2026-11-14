"""Find which ATS board (if any) a company hosts its openings on.

Given a company name, guess plausible board slugs ("Monte Carlo Data" ->
``montecarlodata``, ``monte-carlo-data``, ``montecarlo``...) and probe the
free Greenhouse / Lever / Ashby APIs for each. Greenhouse hits are checked
against the board's declared company name, because short or generic slugs
regularly belong to an unrelated company.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from difflib import SequenceMatcher

from rozgaar.sources import Source, get_source
from rozgaar.sources.greenhouse import Greenhouse

_SUFFIXES = (
    "inc",
    "llc",
    "ltd",
    "corp",
    "corporation",
    "technologies",
    "technology",
    "labs",
    "app",
    "hq",
    "io",
    "co",
    "group",
    "holdings",
)
NAME_MATCH_THRESHOLD = 0.45


@dataclass(frozen=True)
class BoardHit:
    company: str
    source: str
    slug: str
    open_jobs: int


def slug_candidates(company: str) -> list[str]:
    """Plausible board slugs for a company name, most likely first."""
    words = re.sub(r"[^a-z0-9 ]", " ", (company or "").lower()).split()
    if not words:
        return []
    while len(words) > 1 and words[-1] in _SUFFIXES:
        words = words[:-1]
    joined = "".join(words)
    cands = [joined, "-".join(words)]
    for suffix in _SUFFIXES:
        if joined.endswith(suffix) and len(joined) - len(suffix) >= 3:
            cands.append(joined[: -len(suffix)])
    # The first word alone only when it's distinctive enough to be safe.
    if len(words) > 1 and len(words[0]) >= 6:
        cands.append(words[0])
    return [c for c in dict.fromkeys(cands) if len(c) >= 3]


def _same_company(a: str, b: str) -> bool:
    a, b = a.lower(), b.lower()
    return a in b or b in a or SequenceMatcher(None, a, b).ratio() >= NAME_MATCH_THRESHOLD


def find_boards(
    company: str, sources: dict[str, Source] | None = None, pause_s: float = 0.3
) -> list[BoardHit]:
    """Every board that appears to belong to ``company``. Stops at the first
    slug that hits, since a company rarely runs two ATSs."""
    sources = sources or {n: get_source(n) for n in ("greenhouse", "lever", "ashby")}
    for slug in slug_candidates(company):
        hits = []
        for name, src in sources.items():
            n = src.board_size(slug)
            if not n:
                continue
            if isinstance(src, Greenhouse):
                declared = src.board_title(slug)
                if declared and not _same_company(declared, company):
                    continue
            hits.append(BoardHit(company, name, slug, n))
        if hits:
            return hits
        if pause_s:
            time.sleep(pause_s)
    return []
