from __future__ import annotations

from datetime import date

import pytest
import yaml

from rozgaar.config import example_profile_text
from rozgaar.models import Posting
from rozgaar.profile import Profile, parse_profile
from rozgaar.store import Store

TODAY = date(2026, 11, 1)

JD_ANALYST = """About the role
You'll partner with product and finance teams to answer hard questions with data.

Requirements:
- 2+ years of experience in analytics
- Strong SQL and Python
- Experience building dashboards in Tableau or Looker
- Comfortable with stakeholder management

Nice to have:
- dbt
- Experience with Airflow

Benefits
- Great health coverage
"""


@pytest.fixture
def profile_data() -> dict:
    return yaml.safe_load(example_profile_text())


@pytest.fixture
def profile(profile_data) -> Profile:
    return parse_profile(profile_data)


@pytest.fixture
def store() -> Store:
    return Store(":memory:")


def make_posting(**overrides) -> Posting:
    base = dict(
        source="greenhouse",
        board="acme",
        company="Acme",
        title="Data Analyst",
        url="https://boards.greenhouse.io/acme/jobs/1",
        location="New York, NY",
        description=JD_ANALYST,
        posted_on=date(2026, 10, 28),
    )
    base.update(overrides)
    return Posting(**base)


class FakeResponse:
    def __init__(self, status: int, payload=None) -> None:
        self.status_code = status
        self._payload = payload

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class FakeSession:
    """Maps URL prefixes to canned responses; records every request."""

    def __init__(self, routes: dict[str, FakeResponse]) -> None:
        self.routes = routes
        self.calls: list[str] = []
        self.headers: dict = {}

    def get(self, url: str, timeout: float | None = None) -> FakeResponse:
        self.calls.append(url)
        for prefix in sorted(self.routes, key=len, reverse=True):
            if url.startswith(prefix):
                return self.routes[prefix]
        return FakeResponse(404, {})
