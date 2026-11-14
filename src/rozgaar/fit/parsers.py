"""Turn a job description into structured facts (:class:`ParsedJD`).

Two interchangeable parsers:

* :class:`HeuristicParser` needs nothing: it finds known skills in the
  requirements / preferred sections, years from regex, seniority from the
  title. Free, offline and deterministic, but it can only "see" skills that
  are in the shared taxonomy.
* :class:`AnthropicParser` asks a small Claude model for the same structure,
  which catches requirements outside the taxonomy. Results are cached by
  content hash, so a posting is only ever paid for once.

``make_parser`` picks the LLM parser when it's usable and falls back to the
heuristic one otherwise, so the tool always works.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from typing import Protocol

from rozgaar import taxonomy
from rozgaar.filters import min_years_required
from rozgaar.models import ParsedJD, Posting

log = logging.getLogger(__name__)


class Cache(Protocol):
    def get(self, key: str) -> dict | None: ...
    def set(self, key: str, value: dict) -> None: ...


class JDParser(Protocol):
    name: str

    def parse(self, posting: Posting) -> ParsedJD | None: ...


# ---------------------------------------------------------------------------
# helpers shared by both parsers
# ---------------------------------------------------------------------------

_SALARY = re.compile(r"\$\s?(\d{2,3})(?:,(\d{3})|\s?[kK])")


def salary_range(*texts: str) -> tuple[int | None, int | None]:
    """Lowest and highest annual dollar figures mentioned (>= $20k)."""
    values = []
    for text in texts:
        for m in _SALARY.finditer(text or ""):
            thousands = int(m.group(1))
            value = thousands * 1000 + (int(m.group(2)) if m.group(2) else 0)
            if value >= 20_000:
                values.append(value)
    return (min(values), max(values)) if values else (None, None)


_ROLE_FAMILIES = (
    ("ml_engineer", ("machine learning engineer", "ml engineer", "ai engineer")),
    ("data_scientist", ("data scientist", "applied scientist", "research scientist")),
    ("analytics_engineer", ("analytics engineer",)),
    ("data_engineer", ("data engineer",)),
    ("bi_analyst", ("bi analyst", "business intelligence", "bi developer", "reporting analyst")),
    ("data_analyst", ("data analyst", "product analyst", "business analyst", "analyst")),
    ("security", ("security", "grc", "soc analyst", "risk analyst", "compliance")),
    (
        "software_engineer",
        (
            "software engineer",
            "developer",
            "swe",
            "backend",
            "frontend",
            "full stack",
            "full-stack",
        ),
    ),
    ("pm", ("project manager", "program manager", "pmo", "scrum master", "project analyst")),
)


def role_family(title: str) -> str:
    for family, phrases in _ROLE_FAMILIES:
        if any(taxonomy.contains_phrase(title, p) for p in phrases):
            return family
    return "other"


def seniority(title: str, min_years: int | None) -> str:
    t = title.lower()
    if re.search(r"\b(staff|principal|director|head|vp|chief|lead)\b", t):
        return "lead+"
    if re.search(r"\b(senior|sr\.?)\b", t):
        return "senior"
    if re.search(r"\b(intern|junior|jr\.?|entry|associate|new grad|graduate)\b", t):
        return "entry"
    if min_years is not None:
        return "entry" if min_years <= 1 else ("mid" if min_years <= 4 else "senior")
    return "unknown"


def work_mode(*texts: str) -> str:
    blob = " ".join(texts).lower()
    if "hybrid" in blob:
        return "hybrid"
    if re.search(r"\bremote\b", blob):
        return "remote"
    if re.search(r"\b(on-?site|in-office|in office)\b", blob):
        return "onsite"
    return "unclear"


# ---------------------------------------------------------------------------
# heuristic parser
# ---------------------------------------------------------------------------

_REQUIRED_HEADERS = (
    "requirements",
    "qualifications",
    "minimum qualifications",
    "basic qualifications",
    "what you'll need",
    "what you will need",
    "what you need",
    "must have",
    "must-haves",
    "you have",
    "you bring",
    "what we're looking for",
    "what we are looking for",
    "who you are",
    "about you",
    "skills and experience",
)
_PREFERRED_HEADERS = (
    "preferred qualifications",
    "preferred",
    "nice to have",
    "nice-to-have",
    "nice to haves",
    "bonus points",
    "bonus",
    "pluses",
    "a plus",
)
_STOP_HEADERS = (
    "benefits",
    "perks",
    "what we offer",
    "compensation",
    "about us",
    "about the company",
    "equal opportunity",
    "why join",
)


def _header(line: str, headers: tuple[str, ...]) -> bool:
    """A line is a section header when it looks like one (short, not a
    bullet, or ending in a colon) and starts with a known header phrase."""
    raw = line.strip()
    if not raw or raw[0] in "-•*·":
        return False
    low = raw.lower()
    looks_like_header = low.endswith(":") or len(low.split()) <= 4
    return looks_like_header and low.rstrip(":").startswith(headers)


def _sections(text: str) -> tuple[str, str]:
    """Split a JD into (required_text, preferred_text) using header lines.
    If no headers are found, the whole text counts as required."""
    required, preferred, mode = [], [], None
    saw_header = False
    for line in text.splitlines():
        if _header(line, _PREFERRED_HEADERS):
            mode, saw_header = "preferred", True
        elif _header(line, _REQUIRED_HEADERS):
            mode, saw_header = "required", True
        elif _header(line, _STOP_HEADERS):
            mode = None
        elif mode == "required":
            required.append(line)
        elif mode == "preferred":
            preferred.append(line)
    if not saw_header:
        return text, ""
    return "\n".join(required), "\n".join(preferred)


class HeuristicParser:
    name = "heuristic-v1"

    def parse(self, posting: Posting) -> ParsedJD | None:
        text = posting.description or ""
        if len(text) < 80:
            return None
        required_text, preferred_text = _sections(text)
        must_hits = taxonomy.find_terms(required_text)
        must = sorted(must_hits, key=lambda k: -must_hits[k])[:10]
        nice_hits = {
            k: v for k, v in taxonomy.find_terms(preferred_text).items() if k not in must_hits
        }
        nice = sorted(nice_hits, key=lambda k: -nice_hits[k])[:6]
        years = min_years_required(text)
        lo, hi = salary_range(posting.salary_text, text)
        return ParsedJD(
            must_have=must,
            nice_to_have=nice,
            min_years=years,
            seniority=seniority(posting.title, years),
            role_family=role_family(posting.title),
            work_mode=work_mode(posting.location, text),
            salary_min=lo,
            salary_max=hi,
            parser=self.name,
        )


# ---------------------------------------------------------------------------
# LLM parser
# ---------------------------------------------------------------------------

_PROMPT = """Extract structured facts from this job description. Be literal: only \
what the text actually says.

TITLE: {title}
COMPANY: {company}
LOCATION: {location}
DESCRIPTION:
{description}

Return raw JSON only, no code fences:
{{
 "min_years": <int or null: minimum years of experience required>,
 "seniority": "<entry|mid|senior|lead+>",
 "must_have": [<up to 10 short skill phrases the JD REQUIRES>],
 "nice_to_have": [<up to 6 preferred / bonus skill phrases>],
 "domain": "<one short phrase, e.g. healthcare, fintech, or null>",
 "salary_min": <int or null>, "salary_max": <int or null>,
 "work_mode": "<remote|hybrid|onsite|unclear>",
 "role_family": "<data_analyst|analytics_engineer|data_scientist|ml_engineer|bi_analyst|\
data_engineer|software_engineer|security|pm|other>"
}}"""

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


class AnthropicParser:
    """Claude-backed parser. Requires the ``anthropic`` package and an
    ``ANTHROPIC_API_KEY`` in the environment."""

    VERSION = "v3"

    def __init__(self, model: str, cache: Cache | None = None, client=None) -> None:
        self.model = model
        self.cache = cache
        self.name = f"anthropic:{model}:{self.VERSION}"
        if client is None:
            import anthropic  # optional dependency

            client = anthropic.Anthropic()
        self.client = client

    def _key(self, posting: Posting) -> str:
        blob = f"{self.name}\n{posting.title}\n{posting.description[:4000]}"
        return "jdparse:" + hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def parse(self, posting: Posting) -> ParsedJD | None:
        if len(posting.description or "") < 80:
            return None
        key = self._key(posting)
        if self.cache is not None and (hit := self.cache.get(key)) is not None:
            return ParsedJD.from_dict(hit)
        prompt = _PROMPT.format(
            title=posting.title,
            company=posting.company,
            location=posting.location or "unspecified",
            description=posting.description[:4000],
        )
        try:
            msg = self.client.messages.create(
                model=self.model, max_tokens=600, messages=[{"role": "user", "content": prompt}]
            )
            data = json.loads(_FENCE.sub("", msg.content[0].text.strip()))
        except Exception as e:  # network, auth, rate limit, malformed JSON
            log.warning("LLM parse failed for %s / %s: %s", posting.company, posting.title, e)
            return None
        parsed = ParsedJD(
            must_have=[str(s) for s in data.get("must_have") or [] if s][:10],
            nice_to_have=[str(s) for s in data.get("nice_to_have") or [] if s][:6],
            min_years=data.get("min_years") if isinstance(data.get("min_years"), int) else None,
            seniority=data.get("seniority") or "unknown",
            role_family=data.get("role_family") or "other",
            domain=data.get("domain") or None,
            work_mode=data.get("work_mode") or "unclear",
            salary_min=data.get("salary_min") if isinstance(data.get("salary_min"), int) else None,
            salary_max=data.get("salary_max") if isinstance(data.get("salary_max"), int) else None,
            parser=self.name,
        )
        if self.cache is not None:
            self.cache.set(key, parsed.to_dict())
        return parsed


def make_parser(model: str, cache: Cache | None = None, use_llm: bool = True) -> JDParser:
    """The best parser available right now."""
    if use_llm and os.getenv("ANTHROPIC_API_KEY"):
        try:
            return AnthropicParser(model, cache)
        except ImportError:
            log.info(
                "`anthropic` not installed; using the heuristic parser "
                "(pip install 'rozgaar[llm]' to enable LLM parsing)"
            )
    return HeuristicParser()
