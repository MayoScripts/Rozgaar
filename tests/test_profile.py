import pytest

from rozgaar.profile import ProfileError, load_profile, parse_profile


def test_example_profile_parses(profile):
    assert profile.name == "Alex Rivera"
    assert "data analyst" in profile.search.roles
    assert profile.boards["greenhouse"] == ("stripe",)
    assert ("lever", "spotify") in profile.board_list()
    assert profile.experience[0].facts[0].tags


def test_skill_phrases_include_taxonomy_aliases(profile):
    phrases = profile.skill_phrases
    assert "postgres" in phrases  # alias of PostgreSQL
    assert "dax" in phrases  # alias of Power BI
    assert "PostgreSQL" in profile.canonical_skills


def test_missing_skills_is_an_error(profile_data):
    profile_data["skills"] = []
    with pytest.raises(ProfileError, match="skills"):
        parse_profile(profile_data)


def test_missing_roles_is_an_error(profile_data):
    profile_data["search"]["roles"] = []
    with pytest.raises(ProfileError, match="roles"):
        parse_profile(profile_data)


def test_unsupported_board_type(profile_data):
    profile_data["boards"]["workday"] = ["acme"]
    with pytest.raises(ProfileError, match="unsupported board"):
        parse_profile(profile_data)


def test_board_slugs_are_normalised_and_deduplicated(profile_data):
    profile_data["boards"] = {"greenhouse": ["Stripe", "stripe", "acme"]}
    assert parse_profile(profile_data).boards["greenhouse"] == ("stripe", "acme")


def test_bad_types_are_reported(profile_data):
    profile_data["skills"] = "Python, SQL"
    with pytest.raises(ProfileError, match="list of strings"):
        parse_profile(profile_data)
    profile_data["skills"] = ["Python"]
    profile_data["search"]["max_years"] = "lots"
    with pytest.raises(ProfileError, match="search"):
        parse_profile(profile_data)


def test_load_profile_missing_file(tmp_path):
    with pytest.raises(ProfileError, match="rozgaar init"):
        load_profile(tmp_path / "nope.yaml")


def test_load_profile_invalid_yaml(tmp_path):
    p = tmp_path / "profile.yaml"
    p.write_text("skills: [unclosed")
    with pytest.raises(ProfileError, match="not valid YAML"):
        load_profile(p)
