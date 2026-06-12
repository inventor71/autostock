"""Step 4 — WatchStore: active/cleared/expired triggers + fired-set (critic#5)."""

from __future__ import annotations

import json

import src.agent.intraday.watch_store as ws_mod
from src.agent.intraday.watch_store import WatchStore


def _store(tmp_path, monkeypatch, et_date="2026-05-30"):
    # Pin the ET date so valid_until / fired rollover are deterministic.
    monkeypatch.setattr(ws_mod, "et_today", lambda: _Date(et_date))
    return WatchStore(tmp_path)


class _Date:
    def __init__(self, s):
        self._s = s

    def isoformat(self):
        return self._s


def test_set_then_active(tmp_path, monkeypatch):
    s = _store(tmp_path, monkeypatch)
    t = s.set("rtx", "close_above", 182.0, intent="tighten")
    active = s.active()
    assert [a.id for a in active] == [t.id]
    assert active[0].symbol == "RTX" and active[0].condition == "close_above"


def test_clear_removes_from_active(tmp_path, monkeypatch):
    s = _store(tmp_path, monkeypatch)
    t = s.set("AAPL", "price_above", 200.0)
    s.clear(t.id)
    assert s.active() == []


def test_expired_excluded(tmp_path, monkeypatch):
    s = _store(tmp_path, monkeypatch, et_date="2026-05-30")
    s.set("AAPL", "price_above", 200.0, valid_until="2026-05-29")  # yesterday
    s.set("MSFT", "price_below", 100.0, valid_until="2026-05-30")  # today -> kept
    syms = {a.symbol for a in s.active()}
    assert syms == {"MSFT"}


def test_malformed_line_skipped(tmp_path, monkeypatch):
    s = _store(tmp_path, monkeypatch)
    s.set("AAPL", "price_above", 200.0)
    with s.path.open("a", encoding="utf-8") as fh:
        fh.write("{not valid json\n")
    assert len(s.active()) == 1  # fail-closed: bad line ignored


def test_fired_once_per_day(tmp_path, monkeypatch):
    s = _store(tmp_path, monkeypatch)
    t = s.set("AAPL", "price_above", 200.0)
    assert s.is_fired(t.id) is False
    s.mark_fired(t.id)
    assert s.is_fired(t.id) is True
    # persisted file is ET-date scoped
    data = json.loads(s.fired_file.read_text())
    assert data["et_date"] == "2026-05-30" and t.id in data["fired_ids"]


def test_fired_resets_on_et_date_rollover(tmp_path, monkeypatch):
    s = _store(tmp_path, monkeypatch, et_date="2026-05-30")
    t = s.set("AAPL", "price_above", 200.0)
    s.mark_fired(t.id)
    assert s.is_fired(t.id) is True
    # next day -> fired set is empty again (re-armable), but the trigger is still active
    s2 = _store(tmp_path, monkeypatch, et_date="2026-05-31")
    assert s2.is_fired(t.id) is False
    assert any(a.id == t.id for a in s2.active())


def test_watch_tool_cli_set_clear_list(tmp_path, monkeypatch):
    # The agent invokes ``python -m src.agent.tools watch ...``; the CLI uses
    # Journal()'s default root, so point that at the temp workspace.
    import src.agent.journal as journal_mod
    import src.agent.tools.__main__ as toolmain

    monkeypatch.setattr(journal_mod, "DEFAULT_ROOT", tmp_path)
    assert toolmain.main(["watch", "set", "AAPL", "price_above", "201.5"]) == 0
    assert (tmp_path / "watch.jsonl").exists()
    assert toolmain.main(["watch", "list"]) == 0
    assert toolmain.main(["watch", "clear", "nope"]) == 0
