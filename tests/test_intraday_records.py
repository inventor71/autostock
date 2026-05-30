"""Step 1 — F3 intraday records: serialization + fail-closed validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.agent.intraday.records import (
    AbnormalMoveSignal,
    FillEvent,
    NewsDiff,
    SnapshotDelta,
    WakeEvent,
    WatchRecord,
    WatchTrigger,
)


def test_watch_trigger_roundtrip_and_symbol_upper():
    wt = WatchTrigger(symbol="rtx", condition="close_above", level=182.0,
                      intent="ADJUST_STOP->tighten", valid_until="2026-05-30")
    assert wt.symbol == "RTX"
    assert wt.is_close_condition is True
    again = WatchTrigger.model_validate_json(wt.model_dump_json())
    assert again.id == wt.id and again.level == 182.0


def test_watch_trigger_rejects_unknown_condition():
    # v1 vocabulary is A+B only (Q2); vwap_cross/volume_spike are deferred.
    with pytest.raises(ValidationError):
        WatchTrigger(symbol="AAPL", condition="vwap_cross", level=1.0)


def test_price_condition_is_not_close():
    wt = WatchTrigger(symbol="AAPL", condition="price_above", level=200.0)
    assert wt.is_close_condition is False


def test_watch_record_set_requires_trigger():
    with pytest.raises(ValidationError):
        WatchRecord(kind="set")  # no trigger
    ok = WatchRecord(kind="set", trigger=WatchTrigger(symbol="AAPL", condition="price_below", level=1.0))
    assert ok.trigger is not None


def test_watch_record_clear_by_id():
    rec = WatchRecord(kind="clear", target_id="abc123")
    assert rec.kind == "clear" and rec.target_id == "abc123"


def test_fill_event_keyed_by_activity_id():
    f = FillEvent(fill_id="act_1", symbol="meta", qty=50, price=631.2, side="buy", kind="entry")
    assert f.symbol == "META" and f.fill_id == "act_1"


def test_snapshot_delta_defaults_empty():
    d = SnapshotDelta()
    assert d.new_fills == [] and d.notes == []


def test_wake_event_entry_inducing_default_false():
    ev = WakeEvent(kind="new_fill", symbol="AAPL", reason="filled 50sh")
    assert ev.entry_inducing is False and ev.kind == "new_fill"


def test_abnormal_and_news_records():
    sig = AbnormalMoveSignal(symbol="AAPL", kind="price", magnitude=3.1, threshold=2.2)
    nd = NewsDiff(symbol="AAPL", headlines=["x"], last_seen_key="k")
    assert sig.kind == "price" and nd.headlines == ["x"]
