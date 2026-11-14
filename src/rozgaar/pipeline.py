"""The discovery pipeline: fetch -> filter -> parse -> grade -> store.

Order matters for cost. Free work (fetching, regex gates, dedup against the
database) runs on everything; the JD parser, which may be a paid API call,
only runs on postings that are new *and* pass every gate.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date

from rozgaar import filters
from rozgaar.fit import SkillMatcher, brief, grade
from rozgaar.fit.parsers import JDParser
from rozgaar.profile import Profile
from rozgaar.sources import BoardNotFound, Source, SourceError, get_source
from rozgaar.store import Store, posting_from_row

log = logging.getLogger(__name__)


@dataclass
class BoardResult:
    source: str
    board: str
    fetched: int = 0
    added: int = 0
    filtered: int = 0
    closed: int = 0
    error: str = ""
    grades: dict[str, int] = field(default_factory=dict)


def scrape(
    profile: Profile,
    store: Store,
    parser: JDParser,
    boards: list[tuple[str, str]] | None = None,
    source_factory: Callable[[str], Source] = get_source,
    today: date | None = None,
    on_board: Callable[[BoardResult], None] | None = None,
) -> list[BoardResult]:
    """Scrape ``boards`` (default: every board in the profile) and store new,
    gate-passing postings with their fit grade."""
    matcher = SkillMatcher(profile)
    known = store.known_urls()
    sources: dict[str, Source] = {}
    results = []

    for source_name, board in boards if boards is not None else profile.board_list():
        res = BoardResult(source_name, board)
        if source_name not in sources:
            sources[source_name] = source_factory(source_name)
        source = sources[source_name]
        try:
            postings = source.fetch(board)
        except BoardNotFound:
            res.error = "board not found"
        except SourceError as e:
            res.error = str(e)
        else:
            res.fetched = len(postings)
            seen = {p.url for p in postings}
            store.touch([u for u in seen if u in known])
            for p in postings:
                if p.url in known:
                    continue
                verdict = filters.check(p, profile.search, today)
                if not verdict.ok:
                    res.filtered += 1
                    log.debug("skip %s @ %s: %s", p.title, p.company, verdict.reason)
                    continue
                if store.has_open_twin(p):
                    continue
                parsed = parser.parse(p)
                fit = grade(parsed, matcher, profile.search.max_years)
                store.add(p, parsed, fit, brief(p, parsed, fit, profile))
                known.add(p.url)
                res.added += 1
                key = fit.grade or "?"
                res.grades[key] = res.grades.get(key, 0) + 1
            res.closed = store.close_missing(source_name, board, seen)
        results.append(res)
        if on_board:
            on_board(res)
    return results


def regrade(
    profile: Profile, store: Store, parser: JDParser, include_closed: bool = False
) -> dict[str, int]:
    """Re-grade stored postings, e.g. after editing your profile's skills.
    Parses are cached, so with the LLM parser this is (nearly) free."""
    matcher = SkillMatcher(profile)
    counts: dict[str, int] = {}
    for row in store.query(include_closed=include_closed):
        p = posting_from_row(row)
        parsed = parser.parse(p)
        fit = grade(parsed, matcher, profile.search.max_years)
        store.update_grade(row["id"], parsed, fit, brief(p, parsed, fit, profile))
        key = fit.grade or "?"
        counts[key] = counts.get(key, 0) + 1
    return counts
