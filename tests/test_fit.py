import pytest

from rozgaar.fit import HeuristicParser, SkillMatcher, brief, grade
from rozgaar.models import ParsedJD
from tests.conftest import make_posting


@pytest.fixture
def matcher(profile):
    return SkillMatcher(profile)


@pytest.mark.parametrize(
    ("requirement", "covered"),
    [
        ("Strong SQL", True),
        ("3+ years of Python and pandas", True),
        ("Postgres", True),  # alias of a profile skill
        ("DAX", True),  # Power BI alias
        ("digital marketing", False),  # 'git' must not match inside 'digital'
        ("excellent written communication", False),  # 'excel' inside 'excellent'
        ("knowledge of employment laws", False),  # 'aws' inside 'laws'
        ("NoSQL databases", False),  # 'sql' inside 'nosql'
        ("Kubernetes", False),
        ("", False),
    ],
)
def test_skill_matcher(matcher, requirement, covered):
    assert matcher.covers(requirement) is covered


def test_grade_a(matcher):
    fit = grade(ParsedJD(must_have=["SQL", "Python", "Tableau", "dbt"]), matcher, 3)
    assert fit.grade == "A" and fit.score == 1.0 and not fit.missing


def test_grade_b_and_c(matcher):
    b = grade(ParsedJD(must_have=["SQL", "Python", "Kubernetes", "Go"]), matcher, 3)
    assert b.grade == "B" and b.missing == ["Kubernetes", "Go"]
    c = grade(ParsedJD(must_have=["Kubernetes", "Terraform", "Rust", "SQL"]), matcher, 3)
    assert c.grade == "C" and c.score == 0.25


def test_nice_to_haves_add_a_small_bonus(matcher):
    base = grade(ParsedJD(must_have=["SQL", "Rust"]), matcher, 3)
    bonus = grade(ParsedJD(must_have=["SQL", "Rust"], nice_to_have=["dbt"]), matcher, 3)
    assert bonus.score == pytest.approx(base.score + 0.10)


def test_out_of_reach_level_is_c(matcher):
    assert grade(ParsedJD(must_have=["SQL"], min_years=7), matcher, 3).grade == "C"
    assert grade(ParsedJD(must_have=["SQL"], seniority="lead+"), matcher, 3).grade == "C"


def test_ungradeable_is_none_not_a_guess(matcher):
    assert grade(None, matcher, 3).grade is None
    assert grade(ParsedJD(must_have=[]), matcher, 3).grade is None


def test_brief_suggests_matching_experience(profile, matcher):
    posting = make_posting()
    parsed = ParsedJD(must_have=["SQL", "dbt", "Kubernetes"], salary_min=90000, salary_max=120000)
    fit = grade(parsed, matcher, 3)
    b = brief(posting, parsed, fit, profile)
    assert b["mirror_keywords"] == ["SQL", "dbt"]
    assert b["gaps"] == ["Kubernetes"]
    assert b["lead_with"][0].startswith("Northwind Logistics: Rewrote nightly SQL")
    assert b["salary_band"] == "$90,000–$120,000"


def test_end_to_end_heuristic_grade(profile, matcher):
    parsed = HeuristicParser().parse(make_posting())
    fit = grade(parsed, matcher, profile.search.max_years)
    assert fit.grade == "A"
    assert "Looker" in fit.missing  # listed as a requirement, not in the profile
