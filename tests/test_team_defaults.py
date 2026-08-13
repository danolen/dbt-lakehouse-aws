"""Default team picker index for %nolen% labels."""

from __future__ import annotations

from team_defaults import default_index, matching_index, matches_my_team


def test_matches_my_team_case_insensitive():
    assert matches_my_team("Nolen OC")
    assert matches_my_team("dan nolen")
    assert matches_my_team("NOLEN")
    assert not matches_my_team("Smith")
    assert not matches_my_team("")
    assert not matches_my_team(None)


def test_default_index_picks_nolen_not_first_alpha():
    owners = ["Adams", "Nolen", "Smith"]
    assert default_index(owners) == 1


def test_matching_index_none_when_no_nolen():
    assert matching_index(["Adams", "Smith"]) is None
    assert matching_index([]) is None
    assert default_index(["Adams", "Smith"]) == 0
    assert default_index([]) == 0


def test_default_index_uses_alias_when_label_has_no_nolen():
    teams = ["Dragons", "Knights", "Tigers"]
    aliases = {"Knights": "Dan Nolen", "Tigers": "Smith"}
    assert default_index(teams, aliases=aliases) == 1
