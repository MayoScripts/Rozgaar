from rozgaar.discover import find_boards, slug_candidates
from rozgaar.sources.greenhouse import Greenhouse
from rozgaar.sources.lever import Lever


def test_slug_candidates_specifics():
    cands = slug_candidates("Monte Carlo Data, Inc.")
    assert cands[0] == "montecarlodata"
    assert "monte-carlo-data" in cands
    # Suffix words are dropped before joining.
    assert slug_candidates("Acme Technologies")[0] == "acme"
    # A short first word alone is too generic to probe.
    assert "new" not in slug_candidates("New York Life")
    assert slug_candidates("") == []
    assert slug_candidates("AB") == []


class FakeGreenhouse(Greenhouse):
    def __init__(self, sizes, titles):
        self.sizes, self.titles = sizes, titles

    def board_size(self, board):
        return self.sizes.get(board, 0)

    def board_title(self, board):
        return self.titles.get(board, "")


class FakeLever(Lever):
    def __init__(self, sizes):
        self.sizes = sizes

    def board_size(self, board):
        return self.sizes.get(board, 0)


def test_find_boards_verifies_greenhouse_names():
    gh = FakeGreenhouse({"acmerobotics": 12}, {"acmerobotics": "Totally Different Co"})
    lever = FakeLever({"acme-robotics": 4})
    hits = find_boards("Acme Robotics", {"greenhouse": gh, "lever": lever}, pause_s=0)
    assert [(h.source, h.slug, h.open_jobs) for h in hits] == [("lever", "acme-robotics", 4)]


def test_find_boards_accepts_matching_name():
    gh = FakeGreenhouse({"acmerobotics": 12}, {"acmerobotics": "Acme Robotics"})
    hits = find_boards("Acme Robotics", {"greenhouse": gh}, pause_s=0)
    assert hits and hits[0].slug == "acmerobotics"


def test_find_boards_none():
    assert find_boards("Nobody", {"lever": FakeLever({})}, pause_s=0) == []
