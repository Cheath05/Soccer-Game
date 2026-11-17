"""Matching the new leagues' clubs across sources (importers/synthetic.py): names, FC 27's clubs
one to one, and Transfermarkt's clubs only in their own country."""

from datetime import date

from footsim.importers.records import SourcePlayer
from footsim.importers.synthetic import (
    EloTable,
    NewLeague,
    _move_ea_clubs,
    ea_pairs,
    load_new_leagues,
    norm,
    same_club,
)


def test_names_lose_accents_case_and_the_usual_prefixes() -> None:
    assert norm("FK Žalgiris Vilnius") == "zalgiris vilnius"
    assert norm("FC") == "fc"  # nothing left but a prefix: kept


def test_the_same_club_is_the_same_words_or_the_start_of_them() -> None:
    assert same_club("Valur", "Valur Reykjavík")
    assert same_club("Qarabağ", "Qarabağ FK")
    assert not same_club("Gorica", "Mladost Donja Gorica")
    assert not same_club("", "Valur")


def test_fc27_clubs_pair_one_to_one() -> None:
    league = NewLeague(key="XXX1", nation="XXX", clubs=["Slavia Prague", "Sparta Prague",
                                                        "Omonia", "Omonia 29M"],
                       ea_names={"Slavia Prague": "Slavia Praha"})
    pairs = ea_pairs(league, ["Slavia Praha", "Sparta Praha", "Omonia Nicosia"])
    assert pairs["Slavia Prague"] == "Slavia Praha"  # by hand
    assert "Sparta Prague" not in pairs  # no name in common, and no `ea_names`
    assert pairs.get("Omonia") == "Omonia Nicosia"  # the one name the start of it
    assert len(set(pairs.values())) == len(pairs)


def test_a_transfermarkt_club_from_another_country_is_never_found() -> None:
    elo = EloTable(rating={1: 1900.0, 2: 1400.0}, games={1: 700, 2: 20},
                   names={1: "Arsenal FC", 2: "Neman Grodno"},
                   countries={1: {"England"}})
    assert elo.find("Arsenal Dzerzhinsk") == 1  # the name alone would take Arsenal
    assert elo.find("Arsenal Dzerzhinsk", "Belarus") is None
    assert elo.find("Neman Grodno", "Belarus") == 2  # seen only in UEFA's rounds: no country
    assert elo.named("Neman Grodno") == 2 and elo.named("Neman") is None


def test_the_hand_written_names_are_well_formed() -> None:
    for league in load_new_leagues():
        assert set(league.tm_names) <= set(league.clubs), league.key
        assert set(league.ea_names) <= set(league.clubs), league.key


def _player(club: str, league: str) -> SourcePlayer:
    return SourcePlayer(source="ea", source_id=f"{league}:{club}", first_name="A", last_name="B",
                        known_as=None, birth_date=date(2000, 1, 1), nationality="Brazil",
                        club=club, league=league, position="CM", alt_positions=[],
                        preferred_foot="right", weak_foot=3, skill_moves=2, height_cm=None,
                        weight_kg=None, source_overall=70, playstyles=[])


def test_a_club_in_another_fc27_league_moves_into_its_own() -> None:
    """Botafogo is under FC 27's "CONMEBOL Sudamericana": with that league in `ea_also`, the club
    of the very same name moves into the league's own FC 27 league, built once, as FC 27 has it;
    the other countries' clubs there stay, even with a name like one of ours."""
    league = NewLeague(key="BRA1", nation="BRA", clubs=["Botafogo", "Bahia", "Juventude"],
                       ea_league="Liga do Brasil", ea_also=["CONMEBOL Sudamericana"])
    players = [_player("Bahia", "Liga do Brasil"), _player("Botafogo", "CONMEBOL Sudamericana"),
               _player("Juventud", "CONMEBOL Sudamericana")]
    paired = ea_pairs(league, ["Bahia"])
    assert _move_ea_clubs(league, players, paired) == {"Botafogo": "Botafogo"}
    assert [p.league for p in players] == ["Liga do Brasil", "Liga do Brasil",
                                           "CONMEBOL Sudamericana"]
    assert _move_ea_clubs(league, players, paired | {"Botafogo": "Botafogo"}) == {}
    brazil = next(lg for lg in load_new_leagues() if lg.key == "BRA1")
    assert brazil.ea_league == "Liga do Brasil" and brazil.ea_also == ["CONMEBOL Sudamericana"]
    assert brazil.level is not None and brazil.club_levels == "values"
