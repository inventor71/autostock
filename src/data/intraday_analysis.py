"""Pattern-existence analysis over stored intraday features (P0 deliverable).

Answers the empirical question behind the feature request: do the conjectured
intraday patterns (opening sell-off that recovers, early surge that fades, gap
fade/fill) have a measurable conditional edge — and, crucially, *how does that
edge drift over time*? The rolling-window view is the honest answer to the user's
own observation that these patterns are non-stationary.

This is deterministic and backtestable: no LLM, no web, just aggregation over the
deterministic features. A hypothesis looking strong overall but unstable across
windows is exactly the overfitting trap to avoid before building anything on it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Hypothesis:
    """A falsifiable conditional-edge claim: ``condition`` -> sign of ``outcome``."""

    name: str
    description: str
    outcome: str  # feature column whose sign/magnitude is the bet
    expected: int  # +1 expects a rise, -1 expects a fall
    condition: Callable[[pd.DataFrame, dict], pd.Series]


# Default tunable thresholds (fractions, not percent).
DEFAULT_PARAMS: dict[str, float] = {"gap_thr": 0.01, "or_thr": 0.005}

DEFAULT_HYPOTHESES: list[Hypothesis] = [
    Hypothesis(
        "gap_down_reversion",
        "Open gaps down beyond gap_thr -> rest of session recovers (open->close up).",
        outcome="oc_ret",
        expected=+1,
        condition=lambda df, p: df["gap_pct"] < -p["gap_thr"],
    ),
    Hypothesis(
        "gap_up_fade",
        "Open gaps up beyond gap_thr -> session fades (open->close down).",
        outcome="oc_ret",
        expected=-1,
        condition=lambda df, p: df["gap_pct"] > p["gap_thr"],
    ),
    Hypothesis(
        "opening_surge_fade",
        "Opening-range surge beyond or_thr -> rest-of-day fades.",
        outcome="rod_ret",
        expected=-1,
        condition=lambda df, p: df["or_ret"] > p["or_thr"],
    ),
    Hypothesis(
        "opening_dip_recover",
        "Opening-range dip beyond or_thr -> rest-of-day recovers.",
        outcome="rod_ret",
        expected=+1,
        condition=lambda df, p: df["or_ret"] < -p["or_thr"],
    ),
]


def with_derived(df: pd.DataFrame) -> pd.DataFrame:
    """Add analysis-only derived columns (rest-of-day return after the opening range)."""
    df = df.copy()
    # rod_ret = (1+oc_ret)/(1+or_ret) - 1, the return from opening-range end to close.
    if "oc_ret" in df and "or_ret" in df:
        df["rod_ret"] = (1.0 + df["oc_ret"]) / (1.0 + df["or_ret"]) - 1.0
    return df


def _t_stat(values: pd.Series) -> float | None:
    n = int(values.count())
    if n < 2:
        return None
    std = float(values.std(ddof=1))
    if std == 0:
        return None
    return round(float(values.mean()) / (std / np.sqrt(n)), 3)


def _summarize(outcomes: pd.Series, expected: int, baseline_mean: float) -> dict:
    outcomes = outcomes.dropna()
    n = int(len(outcomes))
    if n == 0:
        return {"n": 0}
    mean = float(outcomes.mean())
    excess = mean - baseline_mean
    hit_rate = float((np.sign(outcomes) == expected).mean())
    return {
        "n": n,
        "mean_outcome": round(mean, 6),
        "baseline_mean": round(baseline_mean, 6),
        "mean_excess": round(excess, 6),
        "hit_rate": round(hit_rate, 4),
        "t_stat": _t_stat(outcomes),
        "direction_ok": bool(excess * expected > 0),
    }


def evaluate_hypothesis(df: pd.DataFrame, hyp: Hypothesis, params: dict, *, windows: int = 4) -> dict:
    """Conditional-edge summary plus a rolling-window stability view for one hypothesis."""
    outcome_all = df[hyp.outcome].dropna()
    baseline_mean = float(outcome_all.mean()) if len(outcome_all) else 0.0

    mask = hyp.condition(df, params).fillna(False)
    sub = df[mask].sort_values("date")
    summary = _summarize(sub[hyp.outcome], hyp.expected, baseline_mean)

    # Chronological stability: split the condition-true rows into N contiguous
    # windows by date order and report the edge in each (drift = non-stationarity).
    rolling: list[dict] = []
    sub_valid = sub[sub[hyp.outcome].notna()]
    if len(sub_valid) >= windows:
        for idx in np.array_split(np.arange(len(sub_valid)), windows):
            chunk = sub_valid.iloc[idx]
            rolling.append(
                {
                    "date_start": str(chunk["date"].iloc[0]),
                    "date_end": str(chunk["date"].iloc[-1]),
                    "n": int(len(chunk)),
                    "mean_outcome": round(float(chunk[hyp.outcome].mean()), 6),
                    "hit_rate": round(float((np.sign(chunk[hyp.outcome]) == hyp.expected).mean()), 4),
                }
            )

    return {
        "name": hyp.name,
        "description": hyp.description,
        "outcome": hyp.outcome,
        "expected": hyp.expected,
        "summary": summary,
        "rolling": rolling,
    }


def analyze(
    df: pd.DataFrame,
    hypotheses: list[Hypothesis] | None = None,
    params: dict | None = None,
    *,
    windows: int = 4,
) -> dict:
    """Run all hypotheses over the feature DataFrame and return a report dict."""
    hypotheses = hypotheses or DEFAULT_HYPOTHESES
    params = {**DEFAULT_PARAMS, **(params or {})}
    df = with_derived(df)

    meta = {
        "rows": int(len(df)),
        "symbols": int(df["symbol"].nunique()) if "symbol" in df and len(df) else 0,
        "date_min": str(df["date"].min()) if len(df) else None,
        "date_max": str(df["date"].max()) if len(df) else None,
        "params": params,
    }
    results = [evaluate_hypothesis(df, h, params, windows=windows) for h in hypotheses]
    return {"meta": meta, "hypotheses": results}


def to_markdown(report: dict) -> str:
    """Render the report as a compact markdown summary."""
    m = report["meta"]
    lines = [
        "# Intraday pattern-existence report",
        "",
        f"- rows: **{m['rows']}**  symbols: **{m['symbols']}**  "
        f"range: {m['date_min']} → {m['date_max']}",
        f"- params: {m['params']}",
        "",
    ]
    for r in report["hypotheses"]:
        s = r["summary"]
        lines.append(f"## {r['name']}  (outcome `{r['outcome']}`, expected {r['expected']:+d})")
        lines.append(f"_{r['description']}_")
        if s.get("n", 0) == 0:
            lines.append("- no qualifying sessions")
            lines.append("")
            continue
        lines.append(
            f"- n={s['n']}  hit_rate={s['hit_rate']:.2%}  "
            f"mean={s['mean_outcome']:+.4f}  baseline={s['baseline_mean']:+.4f}  "
            f"excess={s['mean_excess']:+.4f}  t={s['t_stat']}  "
            f"direction_ok={s['direction_ok']}"
        )
        if r["rolling"]:
            lines.append("- rolling stability (chronological windows):")
            for w in r["rolling"]:
                lines.append(
                    f"    - {w['date_start']}→{w['date_end']}  n={w['n']}  "
                    f"mean={w['mean_outcome']:+.4f}  hit={w['hit_rate']:.2%}"
                )
        lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    import argparse
    import json
    import sys

    from src.data.intraday_store import IntradayFeatureStore

    parser = argparse.ArgumentParser(prog="python -m src.data.intraday_analysis")
    parser.add_argument("--symbols", nargs="*", default=None, help="default: all stored")
    parser.add_argument("--format", choices=["md", "json"], default="md")
    parser.add_argument("--windows", type=int, default=4)
    parser.add_argument("--gap-thr", type=float, default=DEFAULT_PARAMS["gap_thr"])
    parser.add_argument("--or-thr", type=float, default=DEFAULT_PARAMS["or_thr"])
    args = parser.parse_args(argv)

    df = IntradayFeatureStore().read(symbols=args.symbols)
    report = analyze(
        df,
        params={"gap_thr": args.gap_thr, "or_thr": args.or_thr},
        windows=args.windows,
    )
    if args.format == "json":
        json.dump(report, sys.stdout, indent=2, default=str)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(to_markdown(report) + "\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
