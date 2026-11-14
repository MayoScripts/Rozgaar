from datetime import date

import pytest

from rozgaar.sources import BoardNotFound, SourceError, get_source
from rozgaar.sources.base import html_to_text
from tests.conftest import FakeResponse, FakeSession

GH_JOBS = {
    "jobs": [
        {
            "title": "Data Analyst",
            "absolute_url": "https://boards.greenhouse.io/acme/jobs/1",
            "location": {"name": "New York, NY"},
            "updated_at": "2026-10-20T10:00:00-04:00",
            "content": (
                "&lt;p&gt;Requirements&lt;/p&gt;&lt;ul&gt;&lt;li&gt;SQL&lt;/li&gt;&lt;/ul&gt;"
            ),
        },
        {"title": "", "absolute_url": "https://example.com/missing-title"},
    ]
}

LEVER_POSTINGS = [
    {
        "text": "Product Analyst",
        "hostedUrl": "https://jobs.lever.co/acme/abc",
        "applyUrl": "https://jobs.lever.co/acme/abc/apply",
        "categories": {"location": "Remote"},
        "createdAt": 1793000000000,
        "descriptionPlain": "Analyze product data.",
        "lists": [{"text": "Requirements", "content": "<li>SQL</li><li>Python</li>"}],
        "salaryRange": {"min": 90000, "max": 120000, "currency": "USD"},
    },
]

ASHBY_JOBS = {
    "jobs": [
        {
            "title": "Analytics Engineer",
            "jobUrl": "https://jobs.ashbyhq.com/acme/1",
            "location": "San Francisco",
            "isRemote": True,
            "publishedAt": "2026-10-25T00:00:00Z",
            "descriptionPlain": "dbt and SQL.",
            "compensation": {"compensationTierSummary": "$120K – $150K"},
        },
        {"title": "Hidden", "jobUrl": "https://jobs.ashbyhq.com/acme/2", "isListed": False},
    ]
}


def test_greenhouse_fetch():
    session = FakeSession(
        {
            "https://boards-api.greenhouse.io/v1/boards/acme/jobs": FakeResponse(200, GH_JOBS),
            "https://boards-api.greenhouse.io/v1/boards/acme": FakeResponse(
                200, {"name": "Acme Inc"}
            ),
        }
    )
    [p] = get_source("greenhouse", session).fetch("acme")
    assert p.company == "Acme Inc"
    assert p.location == "New York, NY"
    assert p.posted_on == date(2026, 10, 20)
    assert "Requirements" in p.description and "SQL" in p.description
    assert "<" not in p.description


def test_lever_fetch():
    session = FakeSession(
        {"https://api.lever.co/v0/postings/acme": FakeResponse(200, LEVER_POSTINGS)}
    )
    [p] = get_source("lever", session).fetch("acme")
    assert p.url == "https://jobs.lever.co/acme/abc"
    assert p.company == "Acme"
    assert p.salary_text == "USD 90,000–120,000"
    assert "Python" in p.description  # pulled in from `lists`


def test_ashby_fetch_skips_unlisted():
    session = FakeSession(
        {"https://api.ashbyhq.com/posting-api/job-board/acme": FakeResponse(200, ASHBY_JOBS)}
    )
    [p] = get_source("ashby", session).fetch("acme")
    assert p.location == "San Francisco (Remote)"
    assert p.salary_text == "$120K – $150K"
    assert p.posted_on == date(2026, 10, 25)


def test_missing_board_and_errors():
    src = get_source("lever", FakeSession({}))
    with pytest.raises(BoardNotFound):
        src.fetch("nope")
    assert src.board_size("nope") == 0
    broken = get_source(
        "ashby",
        FakeSession({"https://api.ashbyhq.com/posting-api/job-board/acme": FakeResponse(500, {})}),
    )
    with pytest.raises(SourceError):
        broken.fetch("acme")


def test_unknown_source():
    with pytest.raises(ValueError):
        get_source("workday")


def test_html_to_text_keeps_structure():
    text = html_to_text("<h2>Requirements</h2><ul><li>SQL &amp; Python</li><li>dbt</li></ul>")
    assert text.splitlines() == ["Requirements", "SQL & Python", "dbt"]
