"""The user profile: everything personal lives here, never in code.

A profile is a single YAML file (see ``examples/profile.example.yaml``). It
holds who you are, what you can do, what you're looking for, and which
company boards to watch. The repository ships only a fictional example; your
real profile lives outside the repo (``~/.rozgaar/profile.yaml`` by default).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from rozgaar import taxonomy

SUPPORTED_BOARDS = ("greenhouse", "lever", "ashby")


class ProfileError(ValueError):
    """The profile file is missing, unreadable, or malformed."""


@dataclass(frozen=True)
class Fact:
    """One true, specific thing you did, tagged with the skills it shows."""

    text: str
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class Experience:
    org: str
    role: str = ""
    facts: tuple[Fact, ...] = ()


@dataclass(frozen=True)
class SearchPrefs:
    roles: tuple[str, ...]
    max_years: int = 3
    max_age_days: int = 30
    us_only: bool = True
    exclude_phrases: tuple[str, ...] = ()
    blocked_companies: tuple[str, ...] = ()


@dataclass(frozen=True)
class Profile:
    name: str
    skills: tuple[str, ...]
    search: SearchPrefs
    boards: dict[str, tuple[str, ...]] = field(default_factory=dict)
    experience: tuple[Experience, ...] = ()
    llm_model: str = "claude-haiku-4-5"

    # -- derived views ---------------------------------------------------

    @property
    def canonical_skills(self) -> frozenset[str]:
        """Profile skills that map onto the shared taxonomy."""
        return frozenset(c for s in self.skills if (c := taxonomy.canonicalize(s)))

    @property
    def skill_phrases(self) -> frozenset[str]:
        """Every phrase that counts as one of your skills: the raw text you
        wrote plus all taxonomy aliases of the skills it resolves to."""
        phrases: set[str] = set()
        for s in self.skills:
            phrases.add(s.strip().lower())
            if canon := taxonomy.canonicalize(s):
                phrases.update(taxonomy.aliases_for(canon))
        return frozenset(p for p in phrases if p)

    def board_list(self) -> list[tuple[str, str]]:
        """``[(ats, slug), ...]`` for every board to scrape."""
        return [(ats, slug) for ats, slugs in self.boards.items() for slug in slugs]


# ---------------------------------------------------------------------------
# loading
# ---------------------------------------------------------------------------


def _str_list(value: Any, where: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ProfileError(f"'{where}' must be a list of strings")
    return tuple(v.strip() for v in value if v.strip())


def _experience(raw: Any) -> tuple[Experience, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ProfileError("'experience' must be a list")
    out = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict) or not item.get("org"):
            raise ProfileError(f"experience[{i}] needs at least an 'org'")
        facts = []
        for j, f in enumerate(item.get("facts") or []):
            if isinstance(f, str):
                facts.append(Fact(text=f))
            elif isinstance(f, dict) and f.get("text"):
                facts.append(
                    Fact(
                        text=f["text"],
                        tags=_str_list(f.get("tags"), f"experience[{i}].facts[{j}].tags"),
                    )
                )
            else:
                raise ProfileError(f"experience[{i}].facts[{j}] needs 'text'")
        out.append(Experience(org=item["org"], role=item.get("role", ""), facts=tuple(facts)))
    return tuple(out)


def _boards(raw: Any) -> dict[str, tuple[str, ...]]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ProfileError("'boards' must map an ATS name to a list of board slugs")
    unknown = set(raw) - set(SUPPORTED_BOARDS)
    if unknown:
        raise ProfileError(
            f"unsupported board type(s): {', '.join(sorted(unknown))} "
            f"(supported: {', '.join(SUPPORTED_BOARDS)})"
        )
    return {
        ats: tuple(dict.fromkeys(s.lower() for s in _str_list(slugs, f"boards.{ats}")))
        for ats, slugs in raw.items()
    }


def parse_profile(data: Any) -> Profile:
    """Build a :class:`Profile` from already-parsed YAML data."""
    if not isinstance(data, dict):
        raise ProfileError("profile must be a YAML mapping")

    candidate = data.get("candidate") or {}
    search = data.get("search") or {}
    if not isinstance(candidate, dict) or not isinstance(search, dict):
        raise ProfileError("'candidate' and 'search' must be mappings")

    skills = _str_list(data.get("skills"), "skills")
    if not skills:
        raise ProfileError("'skills' is empty; fit grading needs at least a few skills")
    roles = _str_list(search.get("roles"), "search.roles")
    if not roles:
        raise ProfileError("'search.roles' is empty; list the job titles you're targeting")

    try:
        prefs = SearchPrefs(
            roles=tuple(r.lower() for r in roles),
            max_years=int(search.get("max_years", 3)),
            max_age_days=int(search.get("max_age_days", 30)),
            us_only=bool(search.get("us_only", True)),
            exclude_phrases=tuple(
                p.lower()
                for p in _str_list(search.get("exclude_phrases"), "search.exclude_phrases")
            ),
            blocked_companies=tuple(
                c.lower()
                for c in _str_list(search.get("blocked_companies"), "search.blocked_companies")
            ),
        )
    except (TypeError, ValueError) as e:
        raise ProfileError(f"invalid value in 'search': {e}") from e

    llm = data.get("llm") or {}
    return Profile(
        name=str(candidate.get("name", "")).strip(),
        skills=skills,
        search=prefs,
        boards=_boards(data.get("boards")),
        experience=_experience(data.get("experience")),
        llm_model=str(llm.get("model", "claude-haiku-4-5")),
    )


def load_profile(path: Path) -> Profile:
    if not path.exists():
        raise ProfileError(f"no profile at {path}; run `rozgaar init` to create one")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise ProfileError(f"{path} is not valid YAML: {e}") from e
    return parse_profile(data)
