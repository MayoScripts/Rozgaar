import pytest

from rozgaar.models import Fit
from rozgaar.store import Store, posting_from_row
from tests.conftest import make_posting


def add(store, n, grade, score, **kw):
    p = make_posting(url=f"https://x.test/{n}", title=f"Data Analyst {n}", **kw)
    store.add(p, None, Fit(grade=grade, score=score, missing=["Go"]), {})
    return p


def test_query_orders_by_grade_then_score(store):
    add(store, 1, "B", 0.5)
    add(store, 2, "A", 0.8)
    add(store, 3, None, None)
    add(store, 4, "A", 0.9)
    add(store, 5, "C", 0.1)
    assert [r["title"][-1] for r in store.query()] == ["4", "2", "1", "3", "5"]
    assert [r["grade"] for r in store.query(grades=("A", "?"))] == ["A", "A", None]


def test_get_by_prefix_and_status(store):
    p = add(store, 1, "A", 0.9)
    assert store.get(p.id[:6])["url"] == p.url
    row = store.set_status(p.id[:6], "shortlisted", note="ask Priya for a referral")
    assert row["status"] == "shortlisted" and row["notes"].startswith("ask")
    assert store.query(statuses=("new",)) == []
    with pytest.raises(ValueError):
        store.set_status(p.id, "ghosted")
    assert store.get("zzzz") is None


def test_close_and_reopen(store):
    a = add(store, 1, "A", 0.9)
    b = add(store, 2, "B", 0.5)
    assert store.close_missing("greenhouse", "acme", {a.url}) == 1
    assert [r["url"] for r in store.query()] == [a.url]
    assert len(store.query(include_closed=True)) == 2
    store.touch([b.url])
    assert len(store.query()) == 2


def test_open_twin_detection(store):
    add(store, 1, "A", 0.9)
    twin = make_posting(url="https://x.test/other-city", title="Data Analyst 1")
    assert store.has_open_twin(twin)
    assert not store.has_open_twin(make_posting(url="https://x.test/9", title="Other"))


def test_round_trip_and_stats(store, tmp_path):
    file_store = Store(tmp_path / "sub" / "r.db")
    p = add(file_store, 1, "A", 0.9)
    row = file_store.get(p.id)
    assert posting_from_row(row) == p
    assert row["fit"]["missing"] == ["Go"]
    s = file_store.stats()
    assert s["open"] == 1 and s["grades"] == {"A": 1} and s["statuses"] == {"new": 1}


def test_cache(store):
    assert store.cache.get("k") is None
    store.cache.set("k", {"a": 1})
    assert store.cache.get("k") == {"a": 1}
