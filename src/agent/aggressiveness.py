"""F85: the aggressiveness knob — single source of truth.

One operator dial (`conservative | balanced | aggressive`, set in
``config/settings.yaml`` ``agent.aggressiveness``) fans out to THREE layers so it
models a day-trading(단타) ↔ long-term-value(장투) philosophy *and* lets the
existing learning loop learn under it:

1. **Prompt disposition** — what the agent hunts and how readily it acts
   (delta-injected into the turn prompts; ``balanced`` injects nothing so the
   shipped behavior is byte-for-byte unchanged).
2. **Deterministic RiskManager preset** — a *named-field overlay* on
   ``settings.risk`` (NEVER a wholesale replacement, so safety gates like
   ``shorting_enabled`` are untouched).
3. **Learning-loop time-axis** — the per-decision grading horizon (stamped onto
   every Decision) and the lesson-recall recency weight.

This module is **pure** (no I/O) so it is trivially unit/property testable. Every
level-specific number/string lives ONLY here — no magic numbers scattered across
risk, prompts, or the learning code.
"""

from __future__ import annotations

from dataclasses import dataclass

# Risk keys this knob is allowed to overlay onto settings.risk. Deliberately a
# strict allowlist: short master toggle (``shorting_enabled``), the short_* params
# and ``individual_stock_halt_pct`` are NOT here, so the overlay can never flip a
# safety gate (F85 FR-6). ``use_bracket_orders`` is a per-call-site kwarg, never an
# overlay key (dropping it would silently disable bracket/OCO protection).
ALLOWED_RISK_KEYS = frozenset({
    "max_position_pct",
    "max_portfolio_risk",
    "max_open_positions",
    "max_stop_distance_pct",
    "atr_stop_multiple",
    "default_risk_reward",
    "take_profit_pct",
    "stop_loss_pct",
    "market_halt_threshold_pct",
})

_LEVELS = ("conservative", "balanced", "aggressive")


@dataclass(frozen=True)
class AggressivenessProfile:
    """Resolved knob settings for one level. Immutable; built once at startup."""

    level: str
    # Named-field overlay merged onto settings.risk (keys ⊆ ALLOWED_RISK_KEYS).
    risk_overlay: dict[str, float]
    # Prompt disposition delta injected into decision-emitting turns. Empty string
    # for ``balanced`` → shipped prompt unchanged.
    disposition: str
    # Replaces/augments the intraday "do not churn" guidance.
    intraday_churn: str
    # Short-appetite tilt, only surfaced when shorting is already enabled (the F60
    # master toggle still gates whether ANY short guidance is shown).
    short_tilt: str
    # Learning time-axis.
    grading_horizon_days: int  # stamped on each Decision; drives the maturity gate
    recall_recency: float  # RecallWeights.recency for lesson recall

    def __post_init__(self) -> None:
        bad = set(self.risk_overlay) - ALLOWED_RISK_KEYS
        if bad:  # guard the SSOT against an accidental safety-gate overlay
            raise ValueError(f"risk_overlay has non-allowlisted keys: {sorted(bad)}")


# ── Prompt disposition blocks (delta only; balanced is intentionally empty) ──

_CONSERVATIVE_DISPOSITION = (
    "## Posture — conservative (long-horizon value)\n"
    "Favor undervalued, fundamentally sound names (low P/E, mean-reversion, "
    "insider/institutional accumulation) over momentum. Enter ONLY on high "
    "conviction; when the setup is unclear, HOLD. Assume a long holding period: "
    "set wide, thesis-based stops and a high reward:risk (aim >= 1:3), and set "
    "`valid_until` long (weeks). Quality over churn — few, well-researched positions."
)

_AGGRESSIVE_DISPOSITION = (
    "## Posture — aggressive (short-horizon momentum)\n"
    "Favor momentum, breakouts, volume surges and same-week catalysts (use "
    "`movers`, intraday action). A moderately-confirmed setup is enough to act — "
    "do not wait for perfect conviction, and do not fear turnover. Trade for a "
    "short-term edge: tight stops, fast profit-taking (reward:risk >= 1:1.5), and "
    "a short `valid_until` (intraday to a few days)."
)

_CONSERVATIVE_CHURN = (
    "Hold through intraday noise — unless the morning plan is broken (a thesis "
    "breach or a planned stop/target is hit), do nothing this turn."
)
_AGGRESSIVE_CHURN = (
    "Act on intraday triggers — a breakout, reversal, or volume spike that fits "
    "your plan is reason to enter or exit now; don't defer a clear short-term move."
)

_AGGRESSIVE_SHORT_TILT = (
    "In a weak tape, lean into the downside as readily as the upside — a broken "
    "or negative-catalyst name is a short candidate, sized for a quick move."
)


# ── The level → parameter table (SSOT). balanced == shipped settings.yaml. ──

PROFILES: dict[str, AggressivenessProfile] = {
    "conservative": AggressivenessProfile(
        level="conservative",
        risk_overlay={
            "max_position_pct": 0.03,
            "max_portfolio_risk": 0.01,
            "max_open_positions": 8,
            "max_stop_distance_pct": 0.08,
            "atr_stop_multiple": 3.5,
            "default_risk_reward": 3.0,
            "take_profit_pct": 0.25,
            "stop_loss_pct": 0.07,
            "market_halt_threshold_pct": -0.02,
        },
        disposition=_CONSERVATIVE_DISPOSITION,
        intraday_churn=_CONSERVATIVE_CHURN,
        short_tilt="",
        grading_horizon_days=45,
        recall_recency=0.25,
    ),
    # balanced overlays NOTHING (empty) and injects NOTHING → identical to the
    # pre-F85 system. Do not add keys here without changing settings.yaml too.
    "balanced": AggressivenessProfile(
        level="balanced",
        risk_overlay={},
        disposition="",
        intraday_churn="",
        short_tilt="",
        grading_horizon_days=20,
        recall_recency=0.5,
    ),
    "aggressive": AggressivenessProfile(
        level="aggressive",
        risk_overlay={
            "max_position_pct": 0.08,
            "max_portfolio_risk": 0.03,
            "max_open_positions": 25,
            "max_stop_distance_pct": 0.15,
            "atr_stop_multiple": 2.0,
            "default_risk_reward": 1.8,
            "take_profit_pct": 0.08,
            "stop_loss_pct": 0.04,
            "market_halt_threshold_pct": -0.05,
        },
        disposition=_AGGRESSIVE_DISPOSITION,
        intraday_churn=_AGGRESSIVE_CHURN,
        short_tilt=_AGGRESSIVE_SHORT_TILT,
        # Short-swing horizon: a 3-day window gives >=2 daily bars so the existing
        # daily-bar learning loop can grade these. Pure same-day scalps still close
        # inside one daily bar and stay ungradeable until intraday price paths land
        # (C2-full, a follow-up track) — aggressive *trades* like a day-trader, and
        # *learns* from its 1-3 day swings.
        grading_horizon_days=3,
        recall_recency=1.0,
    ),
}


def resolve(level: str | None) -> AggressivenessProfile:
    """Return the profile for ``level``; fail-safe to ``balanced`` for any
    unknown/None value (mirrors the config validator so callers never crash)."""
    if level is None:
        return PROFILES["balanced"]
    return PROFILES.get(level.lower(), PROFILES["balanced"])
