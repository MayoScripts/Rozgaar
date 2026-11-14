import json
from types import SimpleNamespace

from rozgaar.fit import parsers
from rozgaar.fit.parsers import AnthropicParser, HeuristicParser, make_parser, salary_range
from tests.conftest import make_posting


def test_heuristic_splits_required_and_preferred():
    parsed = HeuristicParser().parse(make_posting())
    assert {"SQL", "Python", "Tableau", "Looker", "stakeholder management"} <= set(parsed.must_have)
    assert "dbt" in parsed.nice_to_have and "Airflow" in parsed.nice_to_have
    assert "dbt" not in parsed.must_have
    assert parsed.min_years == 2
    assert parsed.role_family == "data_analyst"
    assert parsed.parser == "heuristic-v1"


def test_heuristic_without_headers_uses_whole_text():
    desc = "We use SQL and Python every day to build Tableau dashboards for the team. " * 2
    parsed = HeuristicParser().parse(make_posting(description=desc))
    assert {"SQL", "Python", "Tableau"} <= set(parsed.must_have)


def test_heuristic_does_not_mistake_bullets_for_headers():
    desc = (
        "Requirements:\n"
        "- You have 2+ years of SQL\n"
        "You have shipped Python services\n"
        "Benefits:\n"
        "- Sign-on bonus\n"
        "- Free Tableau training\n"
    )
    parsed = HeuristicParser().parse(make_posting(description=desc + " " * 80))
    assert sorted(parsed.must_have) == ["Python", "SQL"]
    assert parsed.nice_to_have == []  # "Sign-on bonus" is not a preferred-skills header


def test_heuristic_skips_empty_descriptions():
    assert HeuristicParser().parse(make_posting(description="Apply now!")) is None


def test_seniority_and_work_mode():
    assert parsers.seniority("Senior Data Analyst", None) == "senior"
    assert parsers.seniority("Lead Analyst", None) == "lead+"
    assert parsers.seniority("Data Analyst", 1) == "entry"
    assert parsers.seniority("Data Analyst", None) == "unknown"
    assert parsers.work_mode("Hybrid, NYC") == "hybrid"
    assert parsers.work_mode("Remote (US)") == "remote"


def test_salary_range():
    assert salary_range("$95,000 - $120,000 per year") == (95000, 120000)
    assert salary_range("$110k–$140k") == (110000, 140000)
    assert salary_range("401k match, $50 stipend") == (None, None)


class FakeClient:
    def __init__(self, reply: str | Exception) -> None:
        self.reply = reply
        self.calls = 0
        self.messages = self

    def create(self, **kwargs):
        self.calls += 1
        if isinstance(self.reply, Exception):
            raise self.reply
        return SimpleNamespace(content=[SimpleNamespace(text=self.reply)])


class DictCache(dict):
    def set(self, key, value):
        self[key] = value


REPLY = json.dumps(
    {
        "min_years": 2,
        "seniority": "mid",
        "must_have": ["SQL", "Looker"],
        "nice_to_have": ["dbt"],
        "domain": "fintech",
        "salary_min": None,
        "salary_max": None,
        "work_mode": "hybrid",
        "role_family": "data_analyst",
    }
)


def test_anthropic_parser_parses_and_caches():
    client, cache = FakeClient("```json\n" + REPLY + "\n```"), DictCache()
    parser = AnthropicParser("test-model", cache=cache, client=client)
    first = parser.parse(make_posting())
    second = parser.parse(make_posting())
    assert first.must_have == ["SQL", "Looker"] and first.domain == "fintech"
    assert second == first
    assert client.calls == 1  # second call served from cache
    assert first.parser.startswith("anthropic:test-model")


def test_anthropic_parser_failure_returns_none():
    parser = AnthropicParser("m", client=FakeClient(RuntimeError("rate limited")))
    assert parser.parse(make_posting()) is None
    parser = AnthropicParser("m", client=FakeClient("not json"))
    assert parser.parse(make_posting()) is None


def test_make_parser_falls_back_without_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert isinstance(make_parser("m"), HeuristicParser)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    assert isinstance(make_parser("m", use_llm=False), HeuristicParser)
