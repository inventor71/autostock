"""Per-turn telemetry (turns.jsonl): cost/activity of each agent turn.

This is ephemeral data the CLI returns once and then drops — capture it now or
it's gone. Used to track daily LLM spend and how active the agent is (and later
to compare aggressiveness profiles by activity).
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from loguru import logger

# F25: US equity trading day is anchored to the exchange timezone. The local
# (e.g. KST) calendar date splits one ET session across two local dates because
# the regular session crosses local midnight, so we key sessions by ET date.
_MARKET_TZ = ZoneInfo("America/New_York")

_TYPE_PREFIX = {
    "research": "R", "intraday": "I", "wake": "W", "eod": "E", "reconcile": "C",
}
_TYPE_LABEL = {
    "research": "Research", "intraday": "Intraday", "wake": "Wake",
    "eod": "EOD review", "reconcile": "Reconcile",
}
_ID_RE = re.compile(r"^([A-Z])(\d+)$")


def compute_et_date(ts: datetime | str | None = None) -> str:
    """ET trading-day date (YYYY-MM-DD) for an instant.

    A naive datetime/ISO string is interpreted in the machine's local timezone
    (that is how older records were written), then converted to ET. ET extended
    hours (04:00–20:00) never cross ET midnight, so the ET calendar date is the
    trading-session key.
    """
    if ts is None:
        dt = datetime.now().astimezone()
    elif isinstance(ts, str):
        try:
            dt = datetime.fromisoformat(ts)
        except ValueError:
            # Last resort: today's ET date.
            return datetime.now(_MARKET_TZ).date().isoformat()
    else:
        dt = ts
    if dt.tzinfo is None:
        dt = dt.astimezone()  # attach local tz to a naive value
    return dt.astimezone(_MARKET_TZ).date().isoformat()


def generate_turn_id(path: str | Path, turn_type: str) -> str:
    """Type-prefixed session-sequential turn ID (e.g. R1, I3, W1).

    Sequencing is keyed by ET trading date so a session that crosses local
    midnight keeps a single, monotonic ID sequence (F25)."""
    prefix = _TYPE_PREFIX.get(turn_type, "T")
    today_et = compute_et_date()
    max_n = 0
    for rec in read_turns(path):
        rec_et = rec.get("et_date") or compute_et_date(rec.get("ts"))
        if rec_et != today_et:
            continue
        tid = rec.get("turn_id", "")
        m = _ID_RE.match(str(tid))
        if m and m.group(1) == prefix:
            max_n = max(max_n, int(m.group(2)))
    return f"{prefix}{max_n + 1}"


def build_turn_summary(
    turn_type: str,
    decisions,
    llm_text: str = "",
    event_reasons: list[str] | None = None,
) -> str:
    """Build a turn summary enriched with LLM reasoning and event context.

    For turns with decisions, the decisions are listed first, followed by a
    snippet of the LLM's analysis. For turns without decisions (e.g. wake),
    event reasons or the LLM's own summary is used directly.
    """
    label = _TYPE_LABEL.get(turn_type, turn_type.capitalize())

    # Extract a concise snippet from the LLM's output: first 2 non-empty,
    # non-JSON lines that look like analysis (not decisions.jsonl output).
    analysis_lines: list[str] = []
    if llm_text:
        for line in llm_text.split("\n"):
            stripped = line.strip()
            if not stripped or stripped.startswith("{") or stripped.startswith("["):
                continue
            # Skip lines that look like raw JSON fragments or tool output
            if len(stripped) < 10:
                continue
            analysis_lines.append(stripped)
            if len(analysis_lines) >= 3:
                break

    # Build decision list
    decision_parts: list[str] = []
    for d in decisions[:4]:
        sym = getattr(d, "symbol", None) or d.get("symbol", "?") if isinstance(d, dict) else d.symbol
        act = getattr(d, "action", None) or d.get("action", "?") if isinstance(d, dict) else d.action
        conf = getattr(d, "confidence", None) or d.get("confidence") if isinstance(d, dict) else d.confidence
        conf_s = f"({conf:.1f})" if isinstance(conf, (int, float)) else ""
        decision_parts.append(f"{act} {sym}{conf_s}")
    tail = f", +{len(decisions) - 4} more" if len(decisions) > 4 else ""

    lines: list[str] = []

    if decisions:
        lines.append(f"{label}: {', '.join(decision_parts)}{tail}")
        if analysis_lines:
            lines.append("")
            lines.extend(analysis_lines[:2])
    elif event_reasons:
        lines.append(f"{label}: {event_reasons[0]}")
        if len(event_reasons) > 1:
            lines.append(f"  +{len(event_reasons) - 1} more events")
        if analysis_lines:
            lines.append("")
            lines.extend(analysis_lines[:2])
    elif analysis_lines:
        lines.append(f"{label}: {analysis_lines[0]}")
        if len(analysis_lines) > 1:
            lines.extend(analysis_lines[1:2])
    else:
        lines.append(f"{label}: no decisions")

    return "\n".join(lines)


def record_turn(
    path: str | Path,
    *,
    turn_type: str,
    model: str,
    num_decisions: int,
    raw: dict | None,
    turn_id: str = "",
    summary: str = "",
    error: bool = False,
    started_at: str = "",
) -> dict:
    """Append one turn's telemetry (cost/duration/tokens/decisions) as JSONL."""
    raw = raw or {}
    usage = raw.get("usage") or {}
    now = datetime.now().astimezone()  # F25: tz-aware so the TUI can localize
    rec = {
        "turn_id": turn_id,
        "started_at": started_at,
        "ts": now.isoformat(timespec="seconds"),
        "date": now.date().isoformat(),       # local date (kept for back-compat)
        "et_date": compute_et_date(now),       # F25: ET trading-session key
        "turn_type": turn_type,
        "model": model,
        "num_decisions": num_decisions,
        "cost_usd": raw.get("total_cost_usd"),
        "duration_ms": raw.get("duration_ms"),
        "num_turns": raw.get("num_turns"),
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "summary": summary,
        "health": "error" if error else "ok",
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")
    cost = rec["cost_usd"]
    logger.info(
        "Turn telemetry: {} [{}] decisions={} cost={} dur={}ms",
        turn_type, turn_id, num_decisions,
        f"${cost:.4f}" if isinstance(cost, (int, float)) else "n/a",
        rec["duration_ms"],
    )
    return rec


def read_turns(path: str | Path) -> list[dict]:
    path = Path(path)
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out
