"""Money as the user sees it (finance.yaml currencies).

The game keeps euros. The user picks a currency (dollars by default) and the client shows every
amount in it. Prices the user is quoted (values, asking prices, counters, wages asked) are
rounded to market steps in that currency, not in euros, so the figure shown is exactly the
figure paid: $27.5M, not $27.39M shown as $27.4M. An amount typed in the shown currency comes
back as the same euros the client works out (frontend/src/lib/format.ts ``toEuros``).

Only the user's quotes go through here: the AI's own market stays in euros, so a display choice
never changes the world.
"""

import math

from sqlalchemy import Connection

from footsim.transfers.decisions import wage_steps
from footsim.transfers.valuation import quote_eur
from footsim.world.context import World
from footsim.world.meta import read_meta, write_meta


def per_euro(world: World, currency: str) -> float:
    found = world.defs.finance.currencies.get(currency)
    return found.per_euro if found is not None else 1.0


def to_euros(shown: float, rate: float) -> int:
    """An amount in the shown currency, in whole euros: rounded half up, as the client's
    ``Math.round`` does."""
    return math.floor(shown / rate + 0.5)


def quote(eur: float, world: World, currency: str) -> int:
    """A price in euros that reads as a market step in ``currency`` (idempotent)."""
    rate = per_euro(world, currency)
    return to_euros(quote_eur(eur * rate), rate)


def quote_wage(eur: float, world: World, currency: str) -> int:
    """A weekly wage in euros that reads as a club would write it in ``currency``."""
    rate = per_euro(world, currency)
    return to_euros(wage_steps(eur * rate), rate)


def money_text(eur: float, world: World, currency: str) -> str:
    """An amount as the client's ``money()`` shows it: $1.25B, $27.5M, $850K, −£35M."""
    found = world.defs.finance.currencies.get(currency)
    symbol, rate = (found.symbol, found.per_euro) if found is not None else ("€", 1.0)
    value = eur * rate
    sign = "−" if value < 0 else ""
    size = abs(value)
    if size >= 1e9:
        return f"{sign}{symbol}{size / 1e9:.{1 if size >= 1e10 else 2}f}B"
    if size >= 999_950:
        return f"{sign}{symbol}{_trim(size / 1e6)}M"
    if size >= 1_000:
        return f"{sign}{symbol}{math.floor(size / 1_000 + 0.5)}K"
    return f"{sign}{symbol}{math.floor(size + 0.5)}"


def _trim(millions: float) -> str:
    """One decimal, dropped when it's zero: 27.5, 28."""
    text = f"{millions:.1f}"
    return text[:-2] if text.endswith(".0") else text


def set_currency(conn: Connection, world: World, currency: str) -> None:
    """The user's choice of currency, kept with the career."""
    if currency not in world.defs.finance.currencies:
        raise ValueError(f"unknown currency {currency}")
    meta = read_meta(conn)
    meta.currency = currency
    write_meta(conn, meta)
