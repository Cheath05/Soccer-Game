# The market-value model (W4-1)

Fitted 7 Oct 2026 with `footsim fit-values --write`. The coefficients are in `data/config/transfers/valuation.yaml`, and the runtime model is `transfers/valuation.py`.

## Why

Before W4, a player's value was static:
- his Transfermarkt value from the world build (69% of players);
- otherwise a hand-set formula (`estimate_value_eur`).

Neither changed as he developed, aged or moved club. The transfer market needs a value for everyone, every day, that follows the player. So the model is fitted on the Transfermarkt values the world was built from, and then applied to everyone.

## The model

log(value, €) is the sum of:
- an intercept;
- `overall` × (overall − 70);
- `above_knee` × max(0, overall − 85);
- −`decline` × max(0, age − 27);
- −`late_decline` × max(0, age − 31);
- `young` × max(0, 24 − age);
- `young_star` × max(0, overall − 80) × max(0, 28 − age): the premium the market pays for a young star;
- `goalkeeper` × (1 if his best position is GK);
- `reputation` × (his club's reputation − 70).

The shape (the knee at 85, the age turns at 24, 27 and 31, the young-star corner at 80 and 28) is set by hand. The coefficients are fitted by least squares.

**Club reputation stands in for the market he's priced in:** a Premier League player costs more than the same player in Belgium. A free agent is priced at his own reputation, which he carries with him, so his value doesn't collapse the day his contract ends.

**Age is counted in years to the day**, so a value doesn't jump on a birthday.

**Contract time left is not in the value.** It belongs in the asking price (W4-4).

Values are rounded to the steps a market quotes:

| Value | Step |
|---|---|
| Below €1M | €25K |
| €1M to €10M | €100K |
| €10M to €50M | €500K |
| Above €50M | €1M |

The floor is €10K.

## The fit

The sample is every player under contract with a Transfermarkt value in the base world (FC 27, 2026-27): **12,390 players**, with ages (to the day) on 1 July 2026. Rerun it with `footsim fit-values --write` whenever the overall formula, positions or ratings change: `test_valuation.py` fails until you do.

| Term | Coefficient (log) | What it means |
|---|---|---|
| intercept | 14.95 | €3.1M for a 70-rated 24–27-year-old at a reputation-70 club |
| overall | +0.171 | +19% per point |
| above_knee | −0.086 | only +9% per point above 85 |
| decline | 0.141 | −13% a year from 27 |
| late_decline | 0.045 | a further −4% a year from 31 |
| young | +0.110 | +12% per year under 24 |
| young_star | +0.012 | a premium per point over 80 and per year under 28 |
| goalkeeper | −0.431 | keepers are worth 35% less |
| reputation | +0.029 | +3% per point of club reputation |

**R² = 0.741; residual sd = 0.788** (log), so a typical player is within a factor of about 2.2 of his Transfermarkt value.

Median residual by overall (log; positive means the model is below Transfermarkt):

| <65 | 65–75 | 75–82 | 82–86 | 86+ |
|---|---|---|---|---|
| +0.08 | −0.02 | +0.17 | +0.03 | −0.07 |

**Tried and dropped:**
- A squared overall term overvalued the 86+ players by a factor of 1.6 (residual −0.46).
- Without the young-star term, 86+ players under 27 came out 20% low and those over 29 came out 20% high. With it, the young group's median residual is about 0.

## What's lost, and what's not

- **Individual market quirks are lost.** Hype, a contract year, injury history and nationality premiums are in Transfermarkt's numbers but not in the model. The residual sd is the measure of that.
  - The model is the world's consensus price from ratings, age and club.
  - A per-player premium could be kept later if the play-test asks for it.
- **Examples, with the model's value against Transfermarkt's:**

  | Player | Model | Transfermarkt |
  |---|---|---|
  | 86-rated 19-year-old, top club | €219M | €200M |
  | 89-rated 26-year-old | €118M | €200M |
  | 91-rated 27-year-old | €118M | €180M |
  | 75-rated 24-year-old, mid club | €7.3M | |

  So without their fame premium the very best players in their prime come out at about 60% of their Transfermarkt value. W4-3's stored premium restores most of it (see the review notes below).

## Review notes (W4-1 review)

- **Selection.** Transfermarkt values cover 69% of players, mostly the better-known ones. The ones without are rated lower (by club reputation band: 61 v 64 overall in the 30s, 64 v 76 in the 70s), and the model prices them lower accordingly. It can't tell whether they'd be dearer or cheaper than the known players of the same rating.
- **Potential isn't a term.** The design listed the public potential estimate for players up to 23. In the fit, the potential gap above the overall added nothing (−0.003 per point), because the youth and young-star terms already carry what the market pays for youth. So it was left out.
- **The stars' fame premium.** By overall band the model is unbiased: −0.07 at 86+. But Transfermarkt's top 100 sit a median 1.5× above it, because fame and hype aren't in the ratings. Weighting the fit towards the top only trades the bulk's accuracy for part of that gap.
  - W4-3 therefore keeps a per-player market premium instead: his Transfermarkt residual, shrunk, stored once. So the stars keep recognisable prices while the model moves their value with age and form.
- **For W4-4:** club reputation is in the value, so a player's value changes when he moves (from a reputation-55 to a reputation-90 club it rises ×2.75). The seller prices at its own reputation, which the asking price must respect, and the AI shouldn't be able to farm the difference.
- **For W4-8:** loans must not change the value. The value query takes the club from the permanent contract (`kind != 'loan'`).
