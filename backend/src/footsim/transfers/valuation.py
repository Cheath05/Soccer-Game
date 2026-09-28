"""Market value estimate for players without a Transfermarkt value (design §15, first cut)."""

import math

AGE_FACTOR = [(21, 1.4), (24, 1.3), (27, 1.1), (29, 0.9), (31, 0.6), (33, 0.35)]
OLD_FACTOR = 0.2


def estimate_value_eur(overall: float, age: int) -> int:
    factor = next((f for limit, f in AGE_FACTOR if age <= limit), OLD_FACTOR)
    value = 1_000_000 * math.exp(0.24 * (overall - 70)) * factor
    step = 25_000 if value < 1_000_000 else 100_000
    return int(max(25_000, round(value / step) * step))
