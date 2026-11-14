"""Free, deterministic gates that run on every posting before any grading.

Each gate answers "is this posting worth looking at for this profile?" using
only the posting text and the profile's search preferences. Nothing here
costs money or touches the network, so it runs on everything; the (possibly
paid) JD parser only ever sees postings that pass.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from rozgaar.models import Posting
from rozgaar.profile import SearchPrefs
from rozgaar.taxonomy import contains_phrase

# Titles that are out of reach for an early-career search no matter what the
# JD says about years.
HARD_SENIORITY = re.compile(
    r"\b(staff|principal|director|manager|head of|vp|vice president|chief|"
    r"distinguished|fellow|architect)\b",
    re.IGNORECASE,
)
# Titles that may still be in reach if the JD's stated years are low enough.
SOFT_SENIORITY = re.compile(r"\b(senior|sr\.?|lead)\b", re.IGNORECASE)

_YEARS = re.compile(r"(\d{1,2})\s*(?:\+|-\s*\d{1,2}|to\s*\d{1,2})?\s*\+?\s*years?", re.IGNORECASE)
_EXPERIENCE_CONTEXT = ("experience", "years of", "yrs")

# Location markers. A posting fails the US gate only when it names a foreign
# place and no US place; empty/remote/ambiguous locations pass.
FOREIGN_MARKERS = (
    # countries & regions
    "united kingdom",
    "uk",
    "england",
    "scotland",
    "wales",
    "ireland",
    "canada",
    "mexico",
    "brazil",
    "argentina",
    "chile",
    "colombia",
    "peru",
    "uruguay",
    "costa rica",
    "germany",
    "france",
    "netherlands",
    "belgium",
    "luxembourg",
    "switzerland",
    "austria",
    "spain",
    "portugal",
    "italy",
    "greece",
    "denmark",
    "sweden",
    "norway",
    "finland",
    "iceland",
    "poland",
    "czech republic",
    "czechia",
    "hungary",
    "romania",
    "bulgaria",
    "serbia",
    "croatia",
    "ukraine",
    "lithuania",
    "latvia",
    "estonia",
    "turkey",
    "israel",
    "india",
    "pakistan",
    "bangladesh",
    "sri lanka",
    "nepal",
    "china",
    "hong kong",
    "taiwan",
    "japan",
    "korea",
    "south korea",
    "singapore",
    "malaysia",
    "indonesia",
    "thailand",
    "vietnam",
    "philippines",
    "australia",
    "new zealand",
    "uae",
    "united arab emirates",
    "saudi arabia",
    "qatar",
    "egypt",
    "nigeria",
    "kenya",
    "south africa",
    "europe",
    "emea",
    "apac",
    "latam",
    "eu",
    # cities that often appear without their country
    "london",
    "manchester",
    "edinburgh",
    "dublin",
    "toronto",
    "vancouver",
    "montreal",
    "ottawa",
    "calgary",
    "mexico city",
    "sao paulo",
    "são paulo",
    "buenos aires",
    "bogota",
    "berlin",
    "munich",
    "hamburg",
    "paris",
    "amsterdam",
    "brussels",
    "zurich",
    "geneva",
    "vienna",
    "madrid",
    "barcelona",
    "lisbon",
    "milan",
    "rome",
    "athens",
    "copenhagen",
    "stockholm",
    "oslo",
    "helsinki",
    "warsaw",
    "krakow",
    "prague",
    "budapest",
    "bucharest",
    "sofia",
    "belgrade",
    "kyiv",
    "vilnius",
    "tallinn",
    "riga",
    "istanbul",
    "tel aviv",
    "bengaluru",
    "bangalore",
    "mumbai",
    "delhi",
    "new delhi",
    "hyderabad",
    "pune",
    "chennai",
    "gurgaon",
    "gurugram",
    "noida",
    "karachi",
    "lahore",
    "dhaka",
    "beijing",
    "shanghai",
    "shenzhen",
    "taipei",
    "tokyo",
    "osaka",
    "seoul",
    "kuala lumpur",
    "jakarta",
    "bangkok",
    "ho chi minh",
    "hanoi",
    "manila",
    "sydney",
    "melbourne",
    "auckland",
    "dubai",
    "abu dhabi",
    "riyadh",
    "doha",
    "cairo",
    "lagos",
    "nairobi",
    "cape town",
    "johannesburg",
)
US_MARKERS = (
    "united states",
    "usa",
    "u.s.",
    "us",
    "new york",
    "nyc",
    "san francisco",
    "los angeles",
    "seattle",
    "boston",
    "chicago",
    "austin",
    "denver",
    "atlanta",
    "miami",
    "philadelphia",
    "washington",
    "california",
    "texas",
    "new jersey",
    "colorado",
    "massachusetts",
    "illinois",
    "georgia",
    "florida",
)
# "us" is a fine marker in a location field but an ordinary word in prose.
_US_MARKERS_PROSE = tuple(m for m in US_MARKERS if m != "us")
_DECLARED_LOCATION = re.compile(
    r"(based in|located in|position (?:is )?in|office in|on-?site in|work from our)"
    r"\s+([^.\n<]{0,60})",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Verdict:
    ok: bool
    reason: str = ""


PASS = Verdict(True)


def min_years_required(text: str) -> int | None:
    """Smallest years-of-experience figure the text states, else None."""
    if not text:
        return None
    found = []
    for m in _YEARS.finditer(text):
        window = text[max(0, m.start() - 60) : m.end() + 60].lower()
        if any(c in window for c in _EXPERIENCE_CONTEXT):
            found.append(int(m.group(1)))
    return min(found) if found else None


def _mentions_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(contains_phrase(text, m) for m in markers)


def is_us_location(location: str) -> bool:
    """False only when the location clearly points outside the US.
    'Remote - EMEA' is not a US job; 'New York or London' is."""
    if not location or not location.strip():
        return True
    if _mentions_any(location, FOREIGN_MARKERS):
        return _mentions_any(location, US_MARKERS)
    return True


def declared_foreign_location(description: str) -> str:
    """A foreign work location stated in the JD body ('this role is based in
    Bengaluru'), even when the location field is empty or says 'Remote'."""
    for m in _DECLARED_LOCATION.finditer(description or ""):
        context = m.group(2)
        if _mentions_any(context, FOREIGN_MARKERS) and not _mentions_any(
            context, _US_MARKERS_PROSE
        ):
            return m.group(0).strip()[:80]
    return ""


def title_matches_roles(title: str, roles: tuple[str, ...]) -> bool:
    return any(contains_phrase(title, r) for r in roles)


def check(posting: Posting, prefs: SearchPrefs, today: date | None = None) -> Verdict:
    """Run every gate in cheapest-first order; return the first failure."""
    title = posting.title

    if not title_matches_roles(title, prefs.roles):
        return Verdict(False, "title not in target roles")

    company = posting.company.lower()
    for blocked in prefs.blocked_companies:
        if blocked in company:
            return Verdict(False, f"blocked company ({blocked})")

    if HARD_SENIORITY.search(title):
        return Verdict(False, "seniority above target")

    age = posting.age_days(today)
    if age is not None and age > prefs.max_age_days:
        return Verdict(False, f"posted {age} days ago")

    text = f"{title}\n{posting.description}"
    for phrase in prefs.exclude_phrases:
        if contains_phrase(text, phrase):
            return Verdict(False, f"excluded phrase: '{phrase}'")

    if prefs.us_only:
        if not is_us_location(posting.location):
            return Verdict(False, f"non-US location: {posting.location}")
        if declared := declared_foreign_location(posting.description):
            return Verdict(False, f"JD places the role abroad: '{declared}'")

    years = min_years_required(posting.description)
    if SOFT_SENIORITY.search(title) and (years is None or years > prefs.max_years):
        return Verdict(False, f"senior title, JD asks {years if years is not None else '?'} yrs")
    # One year of slack: "4+ years" postings regularly hire at 3.
    if years is not None and years > prefs.max_years + 1:
        return Verdict(False, f"requires {years}+ years")

    return PASS
