"""CLI: python -m src.agent.quality [report]"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

from loguru import logger


def _run_report() -> None:
    from rich.console import Console
    from rich.table import Table

    from src.agent.journal import Journal
    from src.agent.quality.aggregate import rolling, summary
    from src.agent.quality.collector import collect_outcomes

    console = Console()
    journal = Journal()

    if not journal.decisions_file.exists():
        console.print("[yellow]No decisions.jsonl found.[/yellow]")
        return

    console.print("[bold]Collecting decision outcomes...[/bold]")
    outcomes = collect_outcomes(journal)
    if not outcomes:
        console.print("[yellow]No BUY/SELL decisions to analyze.[/yellow]")
        return

    console.print(f"[green]Collected {len(outcomes)} outcomes[/green]")

    s = summary(outcomes)

    table = Table(title="Decision Quality Summary")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="white")

    hr = s["direction_hit_rate"]
    table.add_row("Direction Hit Rate (BUY)", f"{hr['hits']}/{hr['total']} = {hr['rate']:.1%}")
    table.add_row("MAE (avg)", f"{s['mae']['mean']:.2%}" if s["mae"]["count"] else "—")
    table.add_row("MFE (avg)", f"{s['mfe']['mean']:.2%}" if s["mfe"]["count"] else "—")

    sq = s["stop_quality"]
    scored = sq["total"] - sq["n/a"]
    if scored > 0:
        table.add_row(
            "Stop Quality",
            f"{sq['appropriate']} appropriate, {sq['noise_hit']} noise, {sq['held']} held / {scored}",
        )
    else:
        table.add_row("Stop Quality", "—")

    tq = s["target_quality"]
    table.add_row(
        "Target Reached",
        f"{tq['reached_count']}/{tq['total']} ({tq['reach_rate']:.0%})"
        + (f" avg {tq['avg_days_to_reach']:.0f}d" if tq["avg_days_to_reach"] else ""),
    )

    table.add_row(
        "Realized R:R (avg)",
        f"{s['realized_rr']['mean']:.2f}" if s["realized_rr"]["count"] else "—",
    )
    table.add_row(
        "Exit Timing (avg opp cost)",
        f"{s['exit_timing']['mean']:+.2%}" if s["exit_timing"]["count"] else "—",
    )
    table.add_row(
        "Excess vs SPY (avg)",
        f"{s['benchmark_excess_spy']['mean']:+.2%}" if s["benchmark_excess_spy"]["count"] else "—",
    )
    table.add_row(
        "Excess vs QQQ (avg)",
        f"{s['benchmark_excess_qqq']['mean']:+.2%}" if s["benchmark_excess_qqq"]["count"] else "—",
    )

    console.print(table)

    cal = s["confidence_calibration"]
    scored_cal = {k: v for k, v in cal.items() if v["count"] > 0}
    if scored_cal:
        cal_table = Table(title="Confidence Calibration")
        cal_table.add_column("Bucket")
        cal_table.add_column("Count")
        cal_table.add_column("Hit Rate")
        for k, v in scored_cal.items():
            cal_table.add_row(k, str(v["count"]), f"{v['rate']:.0%}")
        console.print(cal_table)

    rolls = rolling(outcomes)
    if rolls:
        console.print(f"\n[bold]Rolling window (20): {len(rolls)} windows[/bold]")
        roll_table = Table(title="Rolling Direction Hit Rate")
        roll_table.add_column("Window")
        roll_table.add_column("Hit Rate")
        for r in rolls[-5:]:
            hr = r["direction_hit_rate"]
            roll_table.add_row(
                f"{r['window_start']}-{r['window_end']}",
                f"{hr['rate']:.0%}" if hr["total"] else "—",
            )
        console.print(roll_table)

    out_dir = journal.root / "quality"
    out_dir.mkdir(exist_ok=True)
    out_file = out_dir / f"{date.today().isoformat()}.json"
    out_file.write_text(json.dumps(s, indent=2, default=str), encoding="utf-8")
    console.print(f"\n[dim]Saved to {out_file}[/dim]")


def main() -> None:
    logger.remove()
    logger.add(sys.stderr, level="WARNING")
    _run_report()


if __name__ == "__main__":
    main()
