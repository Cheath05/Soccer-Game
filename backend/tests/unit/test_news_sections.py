"""The news in sections, and the news the user follows (college fixes, 20 Nov)."""

from footsim.api.news import news_sections
from footsim.world.news_scope import NewsScope


def test_the_news_comes_in_sections_with_each_conference_on_one_line() -> None:
    messages = [
        "Vermont Catamounts win the America East regular season.",
        "UMBC Retrievers win the America East Tournament.",
        "Stanford Cardinal win the ACC regular season.",
        "Stanford Cardinal win the ACC Tournament.",
        "Player development. Improved: Chris Nielsen 52→53.",
        "Your target Danny Las commits to Oregon State Beavers.",
        "The No. 2 recruit, Nicolás Di Cesare (AM), commits to Akron Zips.",
        "Akron Zips win the College Cup: they are the NCAA champions.",
        "Man Utd win the FA Cup.",
        "Man Utd win the FA Cup.",  # once
    ]
    sections = {s.title: s.items for s in news_sections(messages, "UMBC Retrievers")}
    assert list(sections) == ["Your team", "Conference champions", "College soccer",
                              "Recruiting", "Around the world"]
    assert sections["Your team"] == [
        "UMBC Retrievers win the America East Tournament.",
        "Player development. Improved: Chris Nielsen 52→53.",
        "Your target Danny Las commits to Oregon State Beavers."]
    assert sections["Conference champions"] == [
        "ACC: Stanford Cardinal (regular season and tournament)",
        "America East: Vermont Catamounts (regular season), UMBC Retrievers (tournament)"]
    assert sections["College soccer"] == [
        "Akron Zips win the College Cup: they are the NCAA champions."]
    assert sections["Around the world"] == ["Man Utd win the FA Cup."]
    assert news_sections([], None) == []


def test_the_scope_leaves_out_what_the_user_does_not_follow() -> None:
    scope = NewsScope(quiet_leagues=frozenset({"ESP1", "ESP2", "ENG2"}),
                      quiet_nations=frozenset({"ESP"}),
                      league_nations=frozenset({"ESP", "ENG"}), quiet_world=False)
    assert scope.follows_league("ENG1") and not scope.follows_league("ENG2")
    assert scope.follows_nation("ENG") and not scope.follows_nation("ESP")
    assert scope.follows_nation("CAN")  # no league of its own: followed with any league
    college = NewsScope(quiet_leagues=frozenset({"ENG1"}), quiet_nations=frozenset({"ENG"}),
                        league_nations=frozenset({"ENG"}), quiet_world=True)
    assert not college.follows_nation("CAN") and not college.follows_league("ENG1")
