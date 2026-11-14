from dataclasses import replace

from rozgaar.fit import HeuristicParser
from rozgaar.pipeline import regrade, scrape
from rozgaar.sources import BoardNotFound, Source
from tests.conftest import TODAY, make_posting


class FakeSource(Source):
    name = "greenhouse"

    def __init__(self, boards):
        super().__init__(session=object())
        self.boards = boards

    def fetch(self, board):
        if board not in self.boards:
            raise BoardNotFound(board)
        return list(self.boards[board])

    def board_size(self, board):
        return len(self.boards.get(board, []))


class CountingParser(HeuristicParser):
    def __init__(self):
        self.calls = 0

    def parse(self, posting):
        self.calls += 1
        return super().parse(posting)


def run(profile, store, source, parser, boards=(("greenhouse", "acme"),)):
    return scrape(
        profile,
        store,
        parser,
        boards=list(boards),
        source_factory=lambda _name: source,
        today=TODAY,
    )


def test_scrape_stores_graded_postings_and_filters_the_rest(profile, store):
    good = make_posting(url="https://x.test/1")
    off_target = make_posting(url="https://x.test/2", title="Account Executive")
    abroad = make_posting(url="https://x.test/3", location="London, UK")
    source = FakeSource({"acme": [good, off_target, abroad]})
    [res] = run(profile, store, source, CountingParser())
    assert (res.fetched, res.added, res.filtered) == (3, 1, 2)
    assert res.grades == {"A": 1}
    assert store.get(good.id)["grade"] == "A"


def test_rescrape_does_not_reparse_and_closes_removed(profile, store):
    a, b = (
        make_posting(url="https://x.test/a", title="Data Analyst"),
        make_posting(url="https://x.test/b", title="Product Analyst"),
    )
    parser = CountingParser()
    source = FakeSource({"acme": [a, b]})
    run(profile, store, source, parser)
    assert parser.calls == 2

    source.boards["acme"] = [a]  # b came down
    [res] = run(profile, store, source, parser)
    assert parser.calls == 2  # nothing new to parse
    assert res.added == 0 and res.closed == 1
    assert [r["url"] for r in store.query()] == [a.url]


def test_location_twins_are_stored_once(profile, store):
    nyc = make_posting(url="https://x.test/nyc")
    sf = make_posting(url="https://x.test/sf", location="San Francisco, CA")
    [res] = run(profile, store, FakeSource({"acme": [nyc, sf]}), CountingParser())
    assert res.added == 1


def test_missing_board_is_reported_not_fatal(profile, store):
    source = FakeSource({"acme": [make_posting()]})
    res = run(
        profile,
        store,
        source,
        CountingParser(),
        boards=[("greenhouse", "ghost"), ("greenhouse", "acme")],
    )
    assert res[0].error == "board not found"
    assert res[1].added == 1


def test_regrade_after_profile_change(profile, store):
    run(profile, store, FakeSource({"acme": [make_posting()]}), CountingParser())
    weaker = replace(profile, skills=("Excel",))
    counts = regrade(weaker, store, HeuristicParser())
    assert counts == {"C": 1}
    assert store.query()[0]["grade"] == "C"
