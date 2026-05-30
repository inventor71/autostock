"""WatchStore — append-only ``workspace/watch.jsonl`` + fired-set (FR-1/FR-5).

Writer = the ``watch`` agent tool (a subprocess; BR-6.1, the sole writer).
Reader = the daemon's WakeDetector. Cross-process append/read is torn-safe via
``read_complete_lines`` (BR-6.3). "Has this trigger fired today?" is tracked NOT
by a byte cursor (which can't express an id-set scoped to an ET date — critic#5)
but by a separate ``watch_fired.json`` = ``{et_date, fired_ids}`` swept at the
ET-midnight daily sweep (BR-6.4/6.5).
"""

from __future__ import annotations

import json
from pathlib import Path

from loguru import logger

from src.agent.intraday.records import WatchCondition, WatchRecord, WatchTrigger
from src.agent.steering.jsonl import atomic_write_text, read_complete_lines
from src.agent.steering.state import today_et


class WatchStore:
    def __init__(self, root: str | Path):
        root = Path(root)
        self.path = root / "watch.jsonl"
        self.fired_file = root / "watch_fired.json"

    # ---- writer side (used by the agent ``watch`` tool, BR-6.1) ----------- #
    def set(self, symbol: str, condition: WatchCondition, level: float, *,
            intent: str = "", valid_until: str | None = None,
            thesis_ref: str | None = None) -> WatchTrigger:
        trigger = WatchTrigger(symbol=symbol, condition=condition, level=level,
                               intent=intent, valid_until=valid_until,
                               thesis_ref=thesis_ref)
        self._append(WatchRecord(kind="set", trigger=trigger))
        return trigger

    def clear(self, target_id: str) -> None:
        self._append(WatchRecord(kind="clear", target_id=target_id))

    def _append(self, record: WatchRecord) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(record.model_dump_json() + "\n")

    # ---- reader side (daemon WakeDetector) -------------------------------- #
    def _records(self) -> list[WatchRecord]:
        lines, _ = read_complete_lines(self.path, 0)  # full torn-safe scan (small file)
        out: list[WatchRecord] = []
        for line in lines:
            try:
                out.append(WatchRecord.model_validate_json(line))
            except Exception:
                continue  # skip malformed line (fail-closed, BR-13)
        return out

    def active(self) -> list[WatchTrigger]:
        """Currently-active triggers: set, not cleared, not past ``valid_until``.

        Fired-today triggers are still 'active' here; the WakeDetector skips
        re-firing them via :meth:`is_fired` (so a clear/expiry is the only way a
        trigger leaves this list)."""
        today = today_et().isoformat()
        cleared: set[str] = set()
        triggers: dict[str, WatchTrigger] = {}
        for rec in self._records():
            if rec.kind == "clear" and rec.target_id:
                cleared.add(rec.target_id)
            elif rec.kind == "set" and rec.trigger is not None:
                triggers[rec.trigger.id] = rec.trigger
        out = []
        for tid, t in triggers.items():
            if tid in cleared:
                continue
            if t.valid_until is not None and t.valid_until < today:
                continue  # expired
            out.append(t)
        return out

    # ---- fired-set (id-set scoped to an ET date, critic#5) ---------------- #
    def _load_fired(self) -> tuple[str, set[str]]:
        today = today_et().isoformat()
        try:
            data = json.loads(self.fired_file.read_text(encoding="utf-8"))
            if data.get("et_date") == today:
                return today, set(data.get("fired_ids", []))
        except Exception:
            pass
        return today, set()  # missing / stale (rolled over) -> empty today

    def is_fired(self, trigger_id: str) -> bool:
        _, fired = self._load_fired()
        return trigger_id in fired

    def mark_fired(self, trigger_id: str) -> None:
        today, fired = self._load_fired()
        if trigger_id in fired:
            return
        fired.add(trigger_id)
        self._write_fired(today, fired)

    def sweep(self) -> None:
        """ET-midnight: reset the fired set to today's empty set if rolled over."""
        today, fired = self._load_fired()  # already today-scoped (rollover -> empty)
        self._write_fired(today, fired)

    def _write_fired(self, et_date: str, fired_ids: set[str]) -> None:
        try:
            atomic_write_text(self.fired_file,
                              json.dumps({"et_date": et_date, "fired_ids": sorted(fired_ids)}))
        except Exception as e:
            logger.warning("watch fired-set persist failed: {}", e)
