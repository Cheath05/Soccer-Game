"""Money as the user sees it (world/money.py): prices quoted as round figures in the user's
currency, so the figure shown is the figure paid."""

import re
from pathlib import Path

import pytest

from footsim.world.context import get_world
from footsim.world.money import money_text, per_euro, quote, quote_wage, to_euros

FORMAT_TS = Path(__file__).parents[3] / "frontend" / "src" / "lib" / "format.ts"


@pytest.mark.parametrize("currency", ["USD", "EUR", "GBP"])
@pytest.mark.parametrize("eur", [12_345, 480_000, 2_310_000, 27_390_000, 64_800_000, 212_000_000])
def test_a_quote_is_a_round_figure_in_the_users_currency(currency: str, eur: int) -> None:
    world = get_world()
    rate = per_euro(world, currency)
    quoted = quote(eur, world, currency)
    shown = quoted * rate
    step = 25_000 if shown < 1e6 else 100_000 if shown < 1e7 else 500_000 if shown < 5e7 \
        else 1_000_000
    assert abs(shown / step - round(shown / step)) < 1e-3  # on a market step, as shown
    assert quote(quoted, world, currency) == quoted  # quoting again changes nothing
    # The client's toEuros of the figure shown is the same euros: what's shown is what's paid.
    assert to_euros(round(shown / step) * step, rate) == quoted


@pytest.mark.parametrize("currency", ["USD", "EUR", "GBP"])
def test_wages_are_written_as_clubs_write_them(currency: str) -> None:
    world = get_world()
    rate = per_euro(world, currency)
    for eur in (1_234, 23_456, 187_300):
        quoted = quote_wage(eur, world, currency)
        shown = round(quoted * rate)
        assert shown % (50 if shown < 5_000 else 500 if shown < 50_000 else 1_000) == 0
        assert quote_wage(quoted, world, currency) == quoted


def test_text_matches_the_clients_money() -> None:
    world = get_world()
    assert money_text(quote(25_000_000, world, "USD"), world, "USD") == "$27.5M"
    assert money_text(50_000_000, world, "EUR") == "€50M"
    assert money_text(800_000, world, "GBP") == "£680K"
    assert money_text(2_000_000_000, world, "EUR") == "€2.00B"
    assert money_text(-35_000_000, world, "GBP") == "−£29.8M"


def test_the_clients_rates_match_the_config() -> None:
    """format.ts keeps the same table as finance.yaml (the server quotes, the client shows)."""
    source = FORMAT_TS.read_text()
    for code, currency in get_world().defs.finance.currencies.items():
        found = re.search(rf"{code}: \{{ symbol: '(.)', perEuro: ([0-9.]+)", source)
        assert found is not None, code
        assert found.group(1) == currency.symbol
        assert float(found.group(2)) == currency.per_euro
