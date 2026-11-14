"""Grade the match between a profile and a parsed job description.

The grade answers "is this a fight the candidate can win?", not "is this a
good job?". It is the share of the JD's must-have requirements the profile
covers, plus a small bonus for nice-to-haves:

    A  >= 0.72   strong match; worth chasing a referral
    B  >= 0.45   plausible; worth a closer read
    C  <  0.45   real gaps, or the JD's level is out of reach
    None         not enough information to grade (no JD text, no requirements)
"""

from __future__ import annotations

from rozgaar import taxonomy
from rozgaar.fit.skills import SkillMatcher
from rozgaar.models import Fit, ParsedJD, Posting
from rozgaar.profile import Profile

GRADE_A = 0.72
GRADE_B = 0.45
NICE_TO_HAVE_WEIGHT = 0.10


def grade(parsed: ParsedJD | None, matcher: SkillMatcher, max_years: int) -> Fit:
    if parsed is None:
        return Fit(grade=None, score=None, reason="no job description to grade")

    if parsed.min_years is not None and parsed.min_years > max_years + 1:
        return Fit(grade="C", score=0.0, reason=f"asks for {parsed.min_years}+ years")
    if parsed.seniority == "lead+":
        return Fit(grade="C", score=0.0, reason="lead-level or above")

    if not parsed.must_have:
        return Fit(grade=None, score=None, reason="no explicit requirements found")

    covered, missing = matcher.split(parsed.must_have)
    nice_covered, _ = matcher.split(parsed.nice_to_have)
    score = len(covered) / len(parsed.must_have)
    if parsed.nice_to_have:
        score += NICE_TO_HAVE_WEIGHT * len(nice_covered) / len(parsed.nice_to_have)
    score = round(min(score, 1.0), 2)

    letter = "A" if score >= GRADE_A else "B" if score >= GRADE_B else "C"
    reason = f"{len(covered)}/{len(parsed.must_have)} must-haves covered"
    if missing:
        reason += "; missing: " + ", ".join(missing[:4])
    return Fit(grade=letter, score=score, covered=covered, missing=missing, reason=reason)


def brief(posting: Posting, parsed: ParsedJD | None, fit: Fit, profile: Profile) -> dict:
    """What to lead with when you reach out or apply: the requirements you
    cover (mirror their wording) and your experience facts that prove them."""
    keywords = fit.covered[:8]
    lead: list[tuple[int, str]] = []
    for exp in profile.experience:
        for fact in exp.facts:
            evidence = (*fact.tags, fact.text)
            overlap = sum(
                1
                for k in keywords
                if any(
                    taxonomy.contains_phrase(e, k) or taxonomy.contains_phrase(k, e)
                    for e in evidence
                )
            )
            if overlap:
                lead.append((overlap, f"{exp.org}: {fact.text}"))
    lead.sort(key=lambda x: -x[0])

    band = ""
    if parsed and parsed.salary_min:
        band = f"${parsed.salary_min:,}" + (
            f"–${parsed.salary_max:,}"
            if parsed.salary_max and parsed.salary_max != parsed.salary_min
            else ""
        )
    return {
        "mirror_keywords": keywords,
        "gaps": fit.missing,
        "lead_with": [text for _, text in lead[:5]],
        "domain": (parsed.domain if parsed else None) or "",
        "salary_band": band,
    }
