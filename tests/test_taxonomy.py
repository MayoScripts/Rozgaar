import pytest

from rozgaar import taxonomy


@pytest.mark.parametrize(
    ("text", "phrase", "expected"),
    [
        ("Experience with Git and CI", "git", True),
        ("digital marketing experience", "git", False),
        ("excellent communication", "excel", False),
        ("Advanced Excel (pivot tables)", "excel", True),
        ("employment laws and regulations", "aws", False),
        ("Deploy on AWS", "aws", True),
        ("MongoDB or other NoSQL stores", "sql", False),
        ("Modern C++ (17/20)", "c++", True),
        ("Run A/B testing programs", "a/b testing", True),
        ("Node.js services", "node.js", True),
    ],
)
def test_contains_phrase_is_whole_word(text, phrase, expected):
    assert taxonomy.contains_phrase(text, phrase) is expected


def test_canonicalize_resolves_aliases():
    assert taxonomy.canonicalize("Postgres") == "PostgreSQL"
    assert taxonomy.canonicalize("powerbi") == "Power BI"
    assert taxonomy.canonicalize("  SKLEARN ") == "scikit-learn"
    assert taxonomy.canonicalize("underwater basket weaving") is None
    assert taxonomy.canonicalize("") is None


def test_ambiguous_names_only_match_through_aliases():
    assert "Go" not in taxonomy.find_terms("Ready to go fast? Let's go.")
    assert "Go" in taxonomy.find_terms("Backend services in Golang")
    assert "R" not in taxonomy.find_terms("R&D team, section R")


def test_find_terms_counts_hits():
    hits = taxonomy.find_terms("SQL daily. More SQL. Some Python.", ["SQL", "Python", "Java"])
    assert hits == {"SQL": 2, "Python": 1}
