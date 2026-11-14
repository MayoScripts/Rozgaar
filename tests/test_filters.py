from dataclasses import replace
from datetime import date

import pytest

from rozgaar import filters
from tests.conftest import TODAY, make_posting


def verdict(profile, **kw):
    return filters.check(make_posting(**kw), profile.search, TODAY)


def test_good_posting_passes(profile):
    assert verdict(profile).ok


def test_title_must_match_a_target_role(profile):
    v = verdict(profile, title="Account Executive")
    assert not v.ok and "title" in v.reason


def test_blocked_company(profile):
    prefs = replace(profile.search, blocked_companies=("acme",))
    v = filters.check(make_posting(company="Acme Defense"), prefs, TODAY)
    assert not v.ok and "blocked" in v.reason


@pytest.mark.parametrize(
    "title", ["Staff Data Analyst", "Data Analyst Manager", "Director, Business Intelligence"]
)
def test_hard_seniority(profile, title):
    assert not verdict(profile, title=title).ok


def test_senior_title_passes_only_with_low_stated_years(profile):
    low = "Requirements:\n- 2+ years of experience with SQL\n" + "x" * 80
    high = "Requirements:\n- 6+ years of experience with SQL\n" + "x" * 80
    assert verdict(profile, title="Senior Data Analyst", description=low).ok
    assert not verdict(profile, title="Senior Data Analyst", description=high).ok
    assert not verdict(profile, title="Senior Data Analyst", description="No years stated.").ok


def test_years_gate_has_one_year_of_slack(profile):  # max_years = 3
    assert verdict(profile, description="4+ years of experience required").ok
    assert not verdict(profile, description="5+ years of experience required").ok


def test_min_years_required():
    assert filters.min_years_required("3-5 years of experience in analytics") == 3
    assert filters.min_years_required("2+ years experience; 5+ years preferred") == 2
    assert filters.min_years_required("Founded 20 years ago in Ohio.") is None
    assert filters.min_years_required("") is None


def test_stale_posting(profile):
    v = verdict(profile, posted_on=date(2026, 8, 1))
    assert not v.ok and "days ago" in v.reason


def test_excluded_phrase(profile):
    v = verdict(profile, description=make_posting().description + "\nActive TS/SCI required.")
    assert not v.ok and "ts/sci" in v.reason


@pytest.mark.parametrize(
    ("location", "us"),
    [
        ("New York, NY", True),
        ("", True),
        ("Remote", True),
        ("Remote - EMEA", False),
        ("London, UK", False),
        ("Bengaluru", False),
        ("Taipei, Taiwan", False),
        ("New York or London", True),
        ("Toronto, Canada", False),
        ("Pittsburgh, PA", True),
    ],
)
def test_is_us_location(location, us):
    assert filters.is_us_location(location) is us


def test_jd_declared_foreign_location(profile):
    desc = make_posting().description + "\nThis position is based in Bangalore, India."
    v = verdict(profile, location="Remote", description=desc)
    assert not v.ok and "abroad" in v.reason


def test_us_gate_can_be_disabled(profile):
    prefs = replace(profile.search, us_only=False)
    assert filters.check(make_posting(location="London, UK"), prefs, TODAY).ok
