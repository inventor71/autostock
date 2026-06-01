"""Tests for F23 signal tools: earnings, insider, analyst_upgrades, institutional, macro, lesson CLI."""

from __future__ import annotations

import json
import tempfile
from datetime import date, datetime
from unittest.mock import MagicMock

import pandas as pd
import pytest

from src.agent.journal import Journal, LessonRecord
from src.agent.tools import market


# -- helpers ---------------------------------------------------------------- #

def _fake_ticker_factory(**kwargs):
    """Build a ticker factory that returns a mock with configurable properties."""
    def factory(symbol):
        t = MagicMock()
        t.info = kwargs.get("info", {})
        t.calendar = kwargs.get("calendar", {})
        t.insider_transactions = kwargs.get("insider_transactions", pd.DataFrame())
        t.upgrades_downgrades = kwargs.get("upgrades_downgrades", pd.DataFrame())
        t.institutional_holders = kwargs.get("institutional_holders", pd.DataFrame())
        if "earnings_dates" in kwargs:
            type(t).earnings_dates = property(lambda self: kwargs["earnings_dates"])
        else:
            type(t).earnings_dates = property(lambda self: (_ for _ in ()).throw(ImportError("lxml")))
        return t
    return factory


# -- fundamentals short interest extension ---------------------------------- #

class TestFundamentalsExtension:
    def test_short_interest_keys_present(self):
        factory = _fake_ticker_factory(info={
            "longName": "Test", "shortRatio": 2.5, "shortPercentOfFloat": 0.08,
            "heldPercentInsiders": 0.01, "heldPercentInstitutions": 0.72,
        })
        result = market.fundamentals("AAPL", ticker_factory=factory)
        assert result["shortRatio"] == 2.5
        assert result["shortPercentOfFloat"] == 0.08
        assert result["heldPercentInsiders"] == 0.01
        assert result["heldPercentInstitutions"] == 0.72

    def test_short_interest_missing_returns_none(self):
        factory = _fake_ticker_factory(info={"longName": "Test"})
        result = market.fundamentals("AAPL", ticker_factory=factory)
        assert result["shortRatio"] is None


# -- earnings --------------------------------------------------------------- #

class TestEarnings:
    def test_basic_calendar(self):
        factory = _fake_ticker_factory(calendar={
            "Earnings Date": datetime(2026, 7, 15),
            "Earnings Average": 2.15,
            "Revenue Average": 94_200_000_000,
        })
        result = market.earnings("AAPL", ticker_factory=factory)
        assert result["symbol"] == "AAPL"
        assert result["next_earnings_date"] == "2026-07-15"
        assert result["consensus_eps"] == 2.15

    def test_empty_calendar(self):
        factory = _fake_ticker_factory(calendar={})
        result = market.earnings("SPY", ticker_factory=factory)
        assert result["symbol"] == "SPY"
        assert "error" in result

    def test_lxml_missing_fallback(self):
        factory = _fake_ticker_factory(
            calendar={"Earnings Date": datetime(2026, 7, 15), "Earnings Average": 2.0},
        )
        result = market.earnings("AAPL", ticker_factory=factory)
        assert "surprise_history" not in result
        assert result["consensus_eps"] == 2.0

    def test_with_earnings_dates(self):
        ed = pd.DataFrame({
            "Reported EPS": [2.20, 1.95],
            "EPS Estimate": [2.15, 2.00],
        }, index=pd.to_datetime(["2026-04-25", "2026-01-30"]))
        factory = _fake_ticker_factory(
            calendar={"Earnings Date": datetime(2026, 7, 15)},
            earnings_dates=ed,
        )
        result = market.earnings("AAPL", ticker_factory=factory)
        assert "surprise_history" in result
        assert len(result["surprise_history"]) == 2
        assert result["surprise_history"][0]["surprise_pct"] is not None

    def test_error_handling(self):
        def boom(symbol):
            raise RuntimeError("network error")
        result = market.earnings("AAPL", ticker_factory=boom)
        assert result["error"] == "network error"

    def test_json_serializable(self):
        factory = _fake_ticker_factory(calendar={
            "Earnings Date": datetime(2026, 7, 15),
            "Earnings Average": 2.15,
        })
        result = market.earnings("AAPL", ticker_factory=factory)
        json.dumps(result, default=str)


# -- insider ---------------------------------------------------------------- #

class TestInsider:
    def test_basic(self):
        df = pd.DataFrame({
            "Insider": ["John CEO", "Jane CFO"],
            "Position": ["CEO", "CFO"],
            "Start Date": ["2026-05-01", "2026-04-15"],
            "Text": ["Purchase", "Sale"],
            "Shares": [50000, 10000],
            "Value": [7_125_000, 1_500_000],
            "URL": ["", ""],
        })
        factory = _fake_ticker_factory(insider_transactions=df)
        result = market.insider("AAPL", ticker_factory=factory)
        assert result["symbol"] == "AAPL"
        assert len(result["transactions"]) == 2
        assert result["summary"]["total_buys"] == 1
        assert result["summary"]["total_sells"] == 1
        assert result["summary"]["largest_buy"]["value"] == 7_125_000

    def test_empty(self):
        factory = _fake_ticker_factory(insider_transactions=pd.DataFrame())
        result = market.insider("SPY", ticker_factory=factory)
        assert result["transactions"] == []

    def test_json_serializable(self):
        factory = _fake_ticker_factory(insider_transactions=pd.DataFrame())
        json.dumps(market.insider("SPY", ticker_factory=factory), default=str)


# -- analyst_upgrades ------------------------------------------------------- #

class TestAnalystUpgrades:
    def test_basic(self):
        df = pd.DataFrame({
            "Firm": ["Goldman", "Morgan Stanley"],
            "ToGrade": ["Buy", "Overweight"],
            "FromGrade": ["Neutral", "Equal-weight"],
            "Action": ["upgrade", "upgrade"],
            "priceTargetAction": ["", ""],
            "currentPriceTarget": [210, 200],
        }, index=pd.to_datetime(["2026-05-29", "2026-05-20"]))
        factory = _fake_ticker_factory(upgrades_downgrades=df)
        result = market.analyst_upgrades("AAPL", ticker_factory=factory)
        assert result["count_upgrade"] == 2
        assert result["count_downgrade"] == 0
        assert result["recent"][0]["firm"] == "Goldman"

    def test_empty(self):
        factory = _fake_ticker_factory(upgrades_downgrades=pd.DataFrame())
        result = market.analyst_upgrades("SPY", ticker_factory=factory)
        assert result["recent"] == []


# -- institutional ---------------------------------------------------------- #

class TestInstitutional:
    def test_basic(self):
        df = pd.DataFrame({
            "Holder": ["Vanguard", "BlackRock", "State Street", "Fidelity", "Berkshire"],
            "pctHeld": [0.082, 0.071, 0.04, 0.035, 0.03],
            "Shares": [1_300_000_000, 1_100_000_000, 630_000_000, 550_000_000, 470_000_000],
            "Date Reported": ["2026-03-31"] * 5,
            "Value": [0] * 5,
        })
        factory = _fake_ticker_factory(institutional_holders=df)
        result = market.institutional("AAPL", ticker_factory=factory)
        assert result["symbol"] == "AAPL"
        assert len(result["top_holders"]) == 5
        assert result["institutional_pct"] > 0

    def test_empty(self):
        factory = _fake_ticker_factory(institutional_holders=pd.DataFrame())
        result = market.institutional("SPY", ticker_factory=factory)
        assert result["top_holders"] == []
        assert result["institutional_pct"] is None


# -- macro ------------------------------------------------------------------ #

class TestMacro:
    def test_basic(self):
        class FakeYF:
            class Ticker:
                def __init__(self, sym):
                    self.sym = sym
                def history(self, period="5d"):
                    return pd.DataFrame({"Close": [100.0, 101.0]})
        result = market.macro(provider=FakeYF())
        assert "treasury_10y" in result
        assert result["treasury_10y"]["price"] == 101.0
        assert result["treasury_10y"]["change_1d_pct"] == 1.0
        assert "as_of" in result

    def test_partial_failure(self):
        class PartialYF:
            class Ticker:
                def __init__(self, sym):
                    self.sym = sym
                def history(self, period="5d"):
                    if self.sym == "^TNX":
                        raise RuntimeError("fail")
                    return pd.DataFrame({"Close": [50.0, 51.0]})
        result = market.macro(provider=PartialYF())
        assert "error" in result["treasury_10y"]
        assert result["gold"]["price"] == 51.0

    def test_json_serializable(self):
        class FakeYF:
            class Ticker:
                def __init__(self, sym): pass
                def history(self, period="5d"):
                    return pd.DataFrame({"Close": [100.0]})
        json.dumps(market.macro(provider=FakeYF()), default=str)


# -- LessonRecord + Journal ------------------------------------------------ #

class TestLessonRecord:
    def test_round_trip(self):
        r = LessonRecord(
            lesson_id="L001", category="entry_timing",
            signal_used="RSI > 75", outcome="reversed -3%",
            takeaway="Don't chase overbought names",
        )
        serialized = r.model_dump_json()
        restored = LessonRecord.model_validate_json(serialized)
        assert restored == r

    def test_defaults(self):
        r = LessonRecord(lesson_id="L001", takeaway="test")
        assert r.category == "other"
        assert r.times_applied == 0
        assert r.date == date.today().isoformat()


class TestJournalLessons:
    def test_append_and_read(self, tmp_path):
        j = Journal(tmp_path)
        j.init()
        r = LessonRecord(lesson_id="L001", category="sizing", takeaway="Size down on earnings")
        j.append_lesson_record(r)
        records = j.read_lessons_jsonl()
        assert len(records) == 1
        assert records[0].lesson_id == "L001"
        assert records[0].takeaway == "Size down on earnings"
        assert "Size down on earnings" in j.read_lessons()

    def test_next_lesson_id_empty(self, tmp_path):
        j = Journal(tmp_path)
        assert j.next_lesson_id() == "L001"

    def test_next_lesson_id_increments(self, tmp_path):
        j = Journal(tmp_path)
        j.init()
        j.append_lesson_record(LessonRecord(lesson_id="L001", takeaway="a"))
        j.append_lesson_record(LessonRecord(lesson_id="L002", takeaway="b"))
        assert j.next_lesson_id() == "L003"

    def test_multiple_appends_atomic(self, tmp_path):
        j = Journal(tmp_path)
        j.init()
        for i in range(5):
            j.append_lesson_record(LessonRecord(lesson_id=f"L{i+1:03d}", takeaway=f"lesson {i}"))
        assert len(j.read_lessons_jsonl()) == 5


# -- Config ---------------------------------------------------------------- #

class TestConfig:
    def test_multi_agent_config_defaults(self):
        from config.config import MultiAgentConfig
        cfg = MultiAgentConfig()
        assert cfg.enabled is False
        assert cfg.mode == "sequential"
        assert cfg.n_agents == 3

    def test_agent_config_timing_defaults(self):
        from config.config import AgentConfig
        cfg = AgentConfig()
        assert cfg.research_start_before_open == 60
        assert cfg.research_end_before_open == 5

    def test_settings_has_multi_agent(self):
        from config.config import Settings
        s = Settings()
        assert hasattr(s, "multi_agent")
        assert s.multi_agent.enabled is False

    def test_settings_has_research_dict(self):
        from config.config import Settings
        s = Settings()
        assert isinstance(s.research, dict)

    def test_settings_from_yaml_dict(self):
        from config.config import Settings
        s = Settings(**{
            "multi_agent": {"enabled": True, "n_agents": 4, "mode": "parallel"},
            "agent": {"research_start_before_open": 90, "research_end_before_open": 10},
        })
        assert s.multi_agent.enabled is True
        assert s.multi_agent.n_agents == 4
        assert s.agent.research_start_before_open == 90


# -- CLI integration (lesson add) ------------------------------------------ #

class TestLessonCLI:
    def test_lesson_add_cli(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AGENT_JOURNAL_ROOT", str(tmp_path))
        Journal(tmp_path).init()
        from src.agent.tools.__main__ import main
        rc = main(["lesson", "add", "--category", "risk_mgmt", "--takeaway", "test lesson"])
        assert rc == 0
        j = Journal(tmp_path)
        records = j.read_lessons_jsonl()
        assert len(records) == 1
        assert records[0].category == "risk_mgmt"
