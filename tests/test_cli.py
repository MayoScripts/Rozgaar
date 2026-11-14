import pytest

from rozgaar import cli
from rozgaar.discover import BoardHit
from rozgaar.models import Fit
from rozgaar.store import Store
from tests.conftest import make_posting


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("ROZGAAR_HOME", str(tmp_path))
    return tmp_path


def seed(home):
    store = Store(home / "rozgaar.db")
    p = make_posting()
    store.add(
        p,
        None,
        Fit(grade="A", score=0.9, covered=["SQL"], missing=["Looker"], reason="1/2"),
        {"lead_with": ["Acme: did a thing"]},
    )
    return p


def test_init_creates_profile_once(home, capsys):
    assert cli.main(["init"]) == 0
    assert (home / "profile.yaml").read_text().startswith("# rozgaar profile")
    assert cli.main(["init"]) == 1
    assert cli.main(["init", "--force"]) == 0


def test_scrape_without_profile_is_a_clean_error(home, capsys):
    assert cli.main(["scrape"]) == 2
    assert "rozgaar init" in capsys.readouterr().err


def test_bad_board_spec(home, capsys):
    cli.main(["init"])
    assert cli.main(["scrape", "--board", "stripe"]) == 2
    assert "ats:slug" in capsys.readouterr().out
    assert cli.main(["scrape", "--board", "workday:acme"]) == 2
    assert "Unknown board type" in capsys.readouterr().out


def test_jobs_show_mark_stats_export(home, capsys):
    p = seed(home)
    assert cli.main(["jobs"]) == 0
    out = capsys.readouterr().out
    assert p.id[:8] in out and "Data Analyst" in out

    assert cli.main(["show", p.id[:6]]) == 0
    out = capsys.readouterr().out
    assert "missing: Looker" in out and "Lead with" in out

    assert cli.main(["mark", p.id[:6], "shortlisted", "--note", "referral: Sam"]) == 0
    assert "shortlisted" in capsys.readouterr().out
    assert cli.main(["mark", "ffff", "applied"]) == 1

    assert cli.main(["stats"]) == 0
    assert "A=1" in capsys.readouterr().out

    assert cli.main(["export"]) == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines[0].startswith("id,grade") and "Looker" in lines[1]


def test_jobs_empty(home, capsys):
    assert cli.main(["jobs"]) == 0
    assert "No postings" in capsys.readouterr().out


def test_discover_prints_profile_snippet(home, capsys, monkeypatch):
    monkeypatch.setattr(
        cli,
        "find_boards",
        lambda company: [BoardHit(company, "greenhouse", "acme", 7)] if company == "Acme" else [],
    )
    assert cli.main(["discover", "Acme", "Nobody"]) == 0
    out = capsys.readouterr().out
    assert "greenhouse:acme  (7 open)" in out
    assert "no Greenhouse / Lever / Ashby board" in out
    assert "greenhouse: [acme]" in out
