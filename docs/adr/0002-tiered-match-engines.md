# ADR 0002: Multi-fidelity match simulation

**Status:** Accepted (2026-09-27)

## Context
The user wants to watch detailed agent-based matches, but the world holds thousands of matches per season. Python can't run a detailed agent engine for all of them.

## Decision
There are three tiers, all producing the same `MatchOutput` contract:
- **Tier 0:** continuous-coordinate 10 Hz agent engine. Used for the user's matches: live 2D view, highlights, instant result.
- **Tier 1:** possession-chain statistical engine for other matches in playable leagues. Its parameters are fitted as a surrogate of Tier 0, and cross-tier distribution tests keep the two consistent.
- **Tier 2:** results-only team-rating model for background leagues.

A match is fully determined by its initial state, seed and ordered command log. Viewers contain no football logic.

## Consequences
- Tier 0 performance gate: 15 s or less headless per match. If profiling plus Numba can't meet it, the kinematics/interception kernel is ported to Rust (PyO3).
- The tier-consistency tests must stay green.
