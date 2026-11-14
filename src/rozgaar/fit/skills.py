"""Decide whether a requirement phrase is covered by the profile's skills."""

from __future__ import annotations

from rozgaar import taxonomy
from rozgaar.profile import Profile


class SkillMatcher:
    """Answers "does the candidate have this?" for one requirement phrase.

    A requirement is covered when

    1. it resolves to a canonical skill the profile also has
       ("Postgres" vs a profile listing "PostgreSQL"), or
    2. one of the profile's skill phrases appears in it as a whole word
       ("3+ years of SQL and Python" is covered by "SQL").

    Whole-word matching is the important part: substring matching makes
    "git" cover "digital", "excel" cover "excellent" and "aws" cover "laws".
    """

    def __init__(self, profile: Profile) -> None:
        self._canonical = profile.canonical_skills
        # Longest first so a specific phrase wins over a generic one; very
        # short phrases are only trusted via the canonical route.
        self._phrases = sorted(
            (p for p in profile.skill_phrases if len(p) >= 2), key=len, reverse=True
        )

    def covers(self, requirement: str) -> bool:
        req = (requirement or "").strip()
        if not req:
            return False
        canon = taxonomy.canonicalize(req)
        if canon and canon in self._canonical:
            return True
        return any(taxonomy.contains_phrase(req, p) for p in self._phrases)

    def split(self, requirements: list[str]) -> tuple[list[str], list[str]]:
        """``(covered, missing)`` preserving input order."""
        covered, missing = [], []
        for r in requirements:
            (covered if self.covers(r) else missing).append(r)
        return covered, missing
