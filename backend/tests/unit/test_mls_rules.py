"""MLS's roster rules (world/mls.py), worked through the 2026 figures of data/config/rules/mls.yaml
with a dollar rate of 1, so every amount reads as MLS publishes it (in cents)."""

from dataclasses import replace

import pytest
import yaml

from footsim.core.paths import config_dir
from footsim.defs.mls import MlsRulesDef
from footsim.world.mls import (
    DP,
    GA,
    HOMEGROWN,
    SENIOR,
    SUPPLEMENTAL,
    U22,
    ClubRules,
    Figures,
    Member,
    assess,
    base_charge,
    buy_downs,
    choose_designations,
    new_problems,
    not_allowed,
    place_newcomer,
    tiers_fit,
)

D = 100  # cents in a dollar


@pytest.fixture(scope="module")
def fig() -> Figures:
    with (config_dir() / "rules" / "mls.yaml").open() as fh:
        return Figures(MlsRulesDef.model_validate(yaml.safe_load(fh)), 1.0)


def club(model: int = 1, tam: int = 2_125_000, gam: int = 3_280_000, slots: int = 8,
         canadian: bool = False) -> ClubRules:
    return ClubRules(model, tam * D, gam * D, slots, canadian)


def player(pid: int, salary: int, *, age: int = 27, designation: str = SENIOR,
           slot: str = SENIOR, international: bool = False, homegrown: bool = False,
           ga: bool = False, signed_age: int | None = None, canadian: bool = False,
           late: bool = False) -> Member:
    return Member(player_id=pid, name=f"P{pid}", wage=salary * D, age=age,
                  signed_age=signed_age if signed_age is not None else age,
                  international=international, canadian=canadian, homegrown=homegrown, ga=ga,
                  late=late, designation=designation, slot=slot)


def squad(n: int, salary: int, start: int = 100) -> list[Member]:
    """``n`` senior players on the same salary."""
    return [player(start + k, salary) for k in range(n)]


def test_the_figures(fig: Figures) -> None:
    assert fig.budget == 6_425_000 * D
    assert fig.max_charge == 803_125 * D
    assert fig.senior_minimum == 113_400 * D
    assert fig.reserve_minimum == 88_025 * D
    assert fig.model(1) == (3, 3)
    assert fig.model(2) == (2, 4)
    assert fig.rules.tam.for_year(2026) == 2_125_000
    assert fig.rules.tam.for_year(2027) == 2_025_000
    assert fig.rules.tam.for_year(2030) == 2_025_000


def test_dollars_convert_at_the_rate() -> None:
    with (config_dir() / "rules" / "mls.yaml").open() as fh:
        rules = MlsRulesDef.model_validate(yaml.safe_load(fh))
    assert Figures(rules, 1.1).budget == round(6_425_000 / 1.1 * D)


def test_designated_player_charges(fig: Figures) -> None:
    # $803,125 for a DP of 24 or more; $200,000 at 21-23; $150,000 at 20 or younger.
    star = player(1, 12_000_000, age=31, designation=DP)
    assert base_charge(fig, star) == 803_125 * D
    assert base_charge(fig, replace(star, age=22)) == 200_000 * D
    assert base_charge(fig, replace(star, age=20)) == 150_000 * D
    # Signed after the secondary window opened: half the charge.
    assert base_charge(fig, replace(star, late=True)) == round(803_125 * D / 2)
    # A DP paid less than his charge is charged his salary.
    assert base_charge(fig, player(2, 120_000, age=19, designation=DP)) == 120_000 * D


def test_u22_charges_and_eligibility(fig: Figures) -> None:
    young = player(1, 700_000, age=20, designation=U22)
    assert base_charge(fig, young) == 150_000 * D
    assert base_charge(fig, replace(young, age=23)) == 200_000 * D
    assert not_allowed(fig, replace(young, age=24, signed_age=21), U22, SENIOR) is None
    assert not_allowed(fig, replace(young, age=24, signed_age=23), U22, SENIOR) is not None
    assert not_allowed(fig, replace(young, age=26, signed_age=21), U22, SENIOR) is not None
    assert not_allowed(fig, replace(young, wage=900_000 * D), U22, SENIOR) is not None


def test_supplemental_roster_is_not_charged(fig: Figures) -> None:
    kid = player(1, 88_025, age=19, designation=SUPPLEMENTAL, slot=SUPPLEMENTAL)
    assert base_charge(fig, kid) == 0


def test_tam_buys_a_charge_down_to_the_maximum(fig: Figures) -> None:
    # A player paid $1,000,000 needs $196,875 of TAM to come down to the maximum charge.
    members = [player(1, 1_000_000), *squad(17, 200_000)]
    charges, unbought = buy_downs(fig, club(), members)
    assert charges[1].tam == 196_875 * D and charges[1].gam == 0
    assert charges[1].charge == 803_125 * D
    assert unbought == []


def test_tam_buys_down_to_its_floor_when_the_budget_needs_it(fig: Figures) -> None:
    # 17 players at $300,000 ($5.1M) and one at $1,500,000: $803,125 after the required buy-down
    # puts the roster at $5,903,125, under the budget, so no more TAM is used. At $340,000 the
    # 17 come to $5.78M and the club is $158,125 over: TAM buys exactly that much more.
    members = [player(1, 1_500_000), *squad(17, 300_000)]
    charges, _ = buy_downs(fig, club(), members)
    assert charges[1].tam == 696_875 * D
    members = [player(1, 1_500_000), *squad(17, 340_000)]
    charges, _ = buy_downs(fig, club(), members)
    assert charges[1].tam == (696_875 + 158_125) * D
    report = assess(fig, club(), members)
    assert report.used == fig.budget and report.compliant


def test_tam_floor_and_ceiling(fig: Figures) -> None:
    # TAM reaches only players paid up to $1,803,125, and no further down than $150,000.
    over = [player(1, 1_200_000), *squad(17, 600_000)]
    charges, _ = buy_downs(fig, club(gam=0), over)
    assert charges[1].charge == 150_000 * D
    assert charges[1].tam == 1_050_000 * D
    high = [player(1, 1_900_000), *squad(17, 100_000)]
    charges, unbought = buy_downs(fig, club(gam=0), high)
    assert charges[1].tam == 0
    assert unbought == [1]


def test_gam_buys_down_by_half_at_most(fig: Figures) -> None:
    # With no TAM left, GAM buys a $700,000 charge down to $350,000 at most.
    members = squad(18, 400_000) + [player(1, 700_000)]
    charges, _ = buy_downs(fig, club(tam=0), members)
    assert charges[1].gam == 350_000 * D
    assert all(c.gam <= c.base // 2 for c in charges.values())


def test_gam_floor(fig: Figures) -> None:
    # A $250,000 charge comes down to $150,000, not $125,000.
    members = squad(18, 400_000, start=200) + [player(1, 250_000)]
    charges, _ = buy_downs(fig, club(tam=0), members)
    assert charges[1].charge >= 150_000 * D


def test_a_player_above_tams_reach_must_be_a_dp(fig: Figures) -> None:
    # $2,500,000 as a senior: GAM halves it to $1,250,000, still above the maximum.
    members = [player(1, 2_500_000), *squad(17, 200_000)]
    report = assess(fig, club(), members)
    assert [p.code for p in report.problems] == ["unbought"]
    report = assess(fig, club(), [replace(members[0], designation=DP), *members[1:]])
    assert report.compliant
    assert report.charges[1].charge == 803_125 * D


def test_empty_senior_slots_are_charged(fig: Figures) -> None:
    # 16 senior players: the two empty slots below 18 cost the senior minimum each.
    report = assess(fig, club(), squad(16, 200_000))
    assert report.empty_slots == 2
    assert report.used == (16 * 200_000 + 2 * 113_400) * D


def test_over_the_budget(fig: Figures) -> None:
    report = assess(fig, club(tam=0, gam=0), squad(20, 330_000))
    assert [p.code for p in report.problems] == ["budget"]
    assert report.problems[0].refusal == ("Over the salary budget by $175,000 after allocation "
                                          "money")


def test_designated_player_slots_by_model(fig: Figures) -> None:
    dps = [player(k, 3_000_000, designation=DP) for k in range(1, 4)]
    members = dps + squad(15, 120_000)
    assert assess(fig, club(model=1), members).compliant
    report = assess(fig, club(model=2), members)
    assert "dp" in [p.code for p in report.problems]
    assert report.problems[0].refusal == "All 2 Designated Player slots are full"


def test_international_slots(fig: Figures) -> None:
    members = [player(k, 150_000, international=k <= 9) for k in range(1, 19)]
    report = assess(fig, club(), members)
    assert [p.code for p in report.problems] == ["international"]
    assert report.problems[0].refusal == "No international slot free"
    assert assess(fig, club(slots=9), members).compliant
    # Homegrown players are domestic: world/mls.py loads them so.


def test_canadian_clubs_keep_three_canadians(fig: Figures) -> None:
    members = [player(k, 150_000, canadian=k <= 2) for k in range(1, 19)]
    assert [p.code for p in assess(fig, club(canadian=True), members).problems] == ["canadian"]
    assert assess(fig, club(canadian=False), members).compliant


def test_roster_slots(fig: Figures) -> None:
    report = assess(fig, club(), squad(21, 100_000))
    assert "senior" in [p.code for p in report.problems]
    supplemental = [player(k, 88_025, age=20, designation=SUPPLEMENTAL, slot=SUPPLEMENTAL)
                    for k in range(1, 12)]
    report = assess(fig, club(), squad(18, 100_000, start=100) + supplemental)
    assert "supplemental" in [p.code for p in report.problems]


def test_supplemental_tiers(fig: Figures) -> None:
    # Slots 21-24 take players on the senior minimum (any age); 25-30 those 24 or younger on
    # the reserve minimum. Five senior-minimum players aged 30 don't fit four slots.
    older = [player(k, 113_400, age=30, designation=SUPPLEMENTAL, slot=SUPPLEMENTAL)
             for k in range(1, 6)]
    assert not tiers_fit(fig, older)
    assert tiers_fit(fig, older[:4])
    young = [player(k, 88_025, age=21, designation=SUPPLEMENTAL, slot=SUPPLEMENTAL)
             for k in range(10, 16)]
    assert tiers_fit(fig, older[:4] + young)
    assert not_allowed(fig, player(1, 200_000), SUPPLEMENTAL, SUPPLEMENTAL) is not None
    # Generation adidas and Homegrown players may earn more there.
    assert not_allowed(fig, player(2, 200_000, ga=True), GA, SUPPLEMENTAL) is None
    assert not_allowed(fig, player(3, 200_000, homegrown=True), HOMEGROWN, SUPPLEMENTAL) is None
    assert not_allowed(fig, player(4, 200_000), HOMEGROWN, SUPPLEMENTAL) is not None


def test_minimum_salaries(fig: Figures) -> None:
    members = [player(1, 100_000), *squad(17, 200_000)]
    report = assess(fig, club(), members)
    assert [p.code for p in report.problems] == ["minimum"]


def test_a_club_chooses_its_designations(fig: Figures) -> None:
    stars = [player(1, 9_000_000), player(2, 4_000_000), player(3, 2_000_000)]
    young = player(4, 700_000, age=20)
    kids = [player(10 + k, 88_025, age=19) for k in range(6)]
    members = stars + [young] + squad(16, 150_000) + kids
    chosen = {m.player_id: m for m in choose_designations(fig, club(), members)}
    assert {p for p, m in chosen.items() if m.designation == DP} == {1, 2, 3}
    assert chosen[4].designation == U22
    assert all(chosen[k.player_id].slot == SUPPLEMENTAL for k in kids)
    report = assess(fig, club(), list(chosen.values()))
    assert report.senior <= 20
    assert report.compliant


def test_model_two_has_two_dps(fig: Figures) -> None:
    members = [player(1, 9_000_000), player(2, 4_000_000), player(3, 750_000, age=21)] + squad(
        16, 150_000)
    chosen = {m.player_id: m for m in choose_designations(fig, club(model=2), members)}
    assert sum(1 for m in chosen.values() if m.designation == DP) == 2
    assert chosen[3].designation == U22


def test_a_newcomer_takes_the_cheapest_place(fig: Figures) -> None:
    members = squad(18, 200_000)
    kid = player(50, 88_025, age=19)
    placed, report = place_newcomer(fig, club(), members, kid)
    assert placed.slot == SUPPLEMENTAL and report.compliant
    star = player(51, 6_000_000)
    placed, report = place_newcomer(fig, club(), members, star)
    assert placed.designation == DP and report.compliant


def test_a_refusal_names_the_new_problem(fig: Figures) -> None:
    dps = [player(k, 3_000_000, designation=DP) for k in range(1, 4)]
    members = dps + squad(15, 120_000)
    before = assess(fig, club(), members)
    _, after = place_newcomer(fig, club(), members, player(9, 5_000_000))
    assert new_problems(before, after)[0].refusal == "All 3 Designated Player slots are full"
