import json
import uuid
from datetime import date, datetime
from types import SimpleNamespace

import pandas as pd
import pytest
from pydantic import ValidationError

from src.agent import prompts
from src.agent.journal import Decision, Journal
from src.agent.orchestrator import AgentTradingLoop, filter_in_universe
from src.agent.session import AgentSession, AgentTurnResult
from src.agent.tools import market


# --------------------------------------------------------------------------- #
# Journal
# --------------------------------------------------------------------------- #
class TestJournal:
    def test_init_creates_tree_and_constitution(self, tmp_path):
        j = Journal(root=tmp_path / "ws")
        j.init()
        assert (tmp_path / "ws" / "positions").is_dir()
        assert (tmp_path / "ws" / "daily").is_dir()
        assert j.regime_file.exists()
        assert j.watchlist_file.exists()
        assert j.lessons_file.exists()
        assert j.claude_md.exists()
        assert "ADVISOR" in j.claude_md.read_text()  # template copied in

    def test_decision_roundtrip(self, tmp_path):
        j = Journal(root=tmp_path / "ws")
        j.append_decision(Decision(symbol="AAPL", action="BUY", confidence=0.8, stop=95.0, target=120.0))
        j.append_decision(Decision(symbol="MSFT", action="HOLD"))
        all_decisions = j.read_decisions()
        assert len(all_decisions) == 2
        assert all_decisions[0].symbol == "AAPL"
        assert all_decisions[0].action == "BUY"
        assert all_decisions[0].stop == 95.0
        assert [d.symbol for d in j.read_decisions(symbol="AAPL")] == ["AAPL"]

    def test_read_decisions_since(self, tmp_path):
        j = Journal(root=tmp_path / "ws")
        j.append_decision(Decision(symbol="OLD", action="HOLD", ts=datetime(2020, 1, 1)))
        j.append_decision(Decision(symbol="NEW", action="HOLD", ts=datetime(2030, 1, 1)))
        recent = j.read_decisions(since=datetime(2025, 1, 1))
        assert [d.symbol for d in recent] == ["NEW"]

    def test_decision_rejects_invalid_action(self):
        with pytest.raises(ValidationError):
            Decision(symbol="AAPL", action="LONG")

    def test_decision_accepts_null_sell_pct_and_confidence(self, tmp_path):
        # Real LLM output sends null for sell_pct on a BUY (and may for others).
        line = (
            '{"ts": "2026-05-27T09:00:00-04:00", "symbol": "AAPL", "action": "BUY",'
            ' "confidence": null, "sell_pct": null, "limit": 295.0, "stop": 280.0,'
            ' "target": 335.0, "reason": "x"}'
        )
        j = Journal(root=tmp_path / "ws")
        j.decisions_file.parent.mkdir(parents=True, exist_ok=True)
        j.decisions_file.write_text(line + "\n")
        decisions = j.read_decisions()
        assert len(decisions) == 1
        assert decisions[0].sell_pct is None
        assert decisions[0].confidence is None
        assert decisions[0].limit == 295.0

    def test_decision_normalizes_symbol(self, tmp_path):
        j = Journal(root=tmp_path / "ws")
        j.append_decision(Decision(symbol="aapl", action="HOLD"))
        assert j.read_decisions()[0].symbol == "AAPL"
        assert [d.symbol for d in j.read_decisions(symbol="aapl")] == ["AAPL"]

    def test_position_roundtrip(self, tmp_path):
        j = Journal(root=tmp_path / "ws")
        j.init()
        assert j.read_position("AAPL") is None
        j.write_position("aapl", "# AAPL thesis\nbuy the dip")
        assert "thesis" in j.read_position("AAPL")
        assert j.list_positions() == ["AAPL"]

    def test_lessons_append(self, tmp_path):
        j = Journal(root=tmp_path / "ws")
        j.init()
        j.append_lesson("Do not widen stops in a downtrend.")
        assert "Do not widen stops" in j.read_lessons()


# --------------------------------------------------------------------------- #
# Market tools (synthetic data, no network)
# --------------------------------------------------------------------------- #
def _bars(n: int = 120, start: float = 100.0) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    close = pd.Series([start + i * 0.5 for i in range(n)], index=idx)
    return pd.DataFrame(
        {
            "open": close * 0.99,
            "high": close * 1.01,
            "low": close * 0.98,
            "close": close,
            "volume": [1_000_000 + i * 1000 for i in range(n)],
        },
        index=idx,
    )


class _FakeProvider:
    def __init__(self, bars: pd.DataFrame):
        self.bars = bars

    def get_bars(self, symbol, timeframe=None, start=None, end=None, limit=100):
        return self.bars.tail(limit)

    def get_latest_price(self, symbol):
        return float(self.bars["close"].iloc[-1])


class TestMarketTools:
    def setup_method(self):
        self.provider = _FakeProvider(_bars(120))

    def test_quote(self):
        q = market.quote("aapl", self.provider)
        assert q["symbol"] == "AAPL"
        assert q["price"] > 0
        assert q["change_1d_pct"] is not None
        assert isinstance(q["volume"], int)

    def test_indicators(self):
        ind = market.indicators("AAPL", self.provider)
        assert "error" not in ind
        assert "rsi_14" in ind
        assert ind["atr_abs"] is not None and ind["atr_abs"] > 0
        # atr_abs should be roughly atr_pct% of close
        assert ind["atr_abs"] == pytest.approx(ind["atr_pct"] / 100 * ind["close"], rel=0.01)

    def test_indicators_insufficient_data(self):
        ind = market.indicators("AAPL", _FakeProvider(_bars(10)))
        assert "error" in ind

    def test_scoreboard(self):
        rows = market.scoreboard(["AAPL", "MSFT"], self.provider)
        assert len(rows) == 2
        assert rows[0]["symbol"] == "AAPL"
        assert "chg_20d" in rows[0]
        assert rows[0]["rsi_14"] is not None

    def test_scoreboard_handles_bad_symbol(self):
        class Boom:
            def get_bars(self, *a, **k):
                raise RuntimeError("boom")

        rows = market.scoreboard(["BAD"], Boom())
        assert rows[0]["error"] == "boom"

    def test_fundamentals(self):
        class FakeTicker:
            def __init__(self, symbol):
                self.symbol = symbol

            @property
            def info(self):
                return {"longName": "Apple Inc", "sector": "Tech", "marketCap": 3e12, "trailingPE": 30.0}

        f = market.fundamentals("AAPL", ticker_factory=FakeTicker)
        assert f["symbol"] == "AAPL"
        assert f["longName"] == "Apple Inc"
        assert f["sector"] == "Tech"

    def test_news_includes_links(self):
        from src.data.providers.news_provider import NewsItem

        class FakeNews:
            def get_news(self, symbol, limit=8):
                return [NewsItem(title="Apple soars", publisher="X", link="http://example/1")]

        n = market.news("AAPL", news_provider=FakeNews())
        assert n["news"][0]["link"] == "http://example/1"
        assert n["news"][0]["title"] == "Apple soars"

    def test_outputs_json_serializable(self):
        import json

        json.dumps(market.quote("AAPL", self.provider))
        json.dumps(market.indicators("AAPL", self.provider))
        json.dumps(market.scoreboard(["AAPL"], self.provider))


class TestToolsCLI:
    def test_cli_quote_dispatch(self, monkeypatch, capsys):
        import json

        from src.agent.tools import __main__ as cli

        monkeypatch.setattr(cli, "_provider", lambda: _FakeProvider(_bars(120)))
        rc = cli.main(["quote", "AAPL"])
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert data["symbol"] == "AAPL"

    def test_cli_scoreboard_uses_explicit_symbols(self, monkeypatch, capsys):
        import json

        from src.agent.tools import __main__ as cli

        monkeypatch.setattr(cli, "_provider", lambda: _FakeProvider(_bars(120)))
        rc = cli.main(["scoreboard", "--symbols", "AAPL", "MSFT"])
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert {row["symbol"] for row in data} == {"AAPL", "MSFT"}


# --------------------------------------------------------------------------- #
# Agent session (no real claude CLI: runner is injected)
# --------------------------------------------------------------------------- #
class _FakeRunner:
    def __init__(self, stdout: str, returncode: int = 0, stderr: str = ""):
        self.calls: list[dict] = []
        self._stdout = stdout
        self._returncode = returncode
        self._stderr = stderr

    def __call__(self, cmd, *, input, cwd, timeout, env=None):
        self.calls.append({"cmd": cmd, "input": input, "cwd": cwd, "timeout": timeout, "env": env})
        return SimpleNamespace(returncode=self._returncode, stdout=self._stdout, stderr=self._stderr)


def _ok_payload(result="done", session_id="srv-sid"):
    return json.dumps({"type": "result", "result": result, "is_error": False, "session_id": session_id})


class TestAgentSession:
    def test_first_turn_creates_session(self, tmp_path):
        runner = _FakeRunner(_ok_payload("wrote AAPL thesis"))
        sess = AgentSession(workspace=tmp_path / "ws", runner=runner)
        res = sess.run_turn("analyze AAPL")

        cmd = runner.calls[0]["cmd"]
        assert "-p" in cmd
        assert cmd[cmd.index("--output-format") + 1] == "json"
        assert "--session-id" in cmd and "--resume" not in cmd
        # allowedTools is one comma-joined arg with web + restricted Bash
        allow = cmd[cmd.index("--allowedTools") + 1]
        assert "WebSearch" in allow
        assert "Bash(python -m src.agent.tools:*)" in allow
        # prompt goes on stdin; cwd is the workspace
        assert runner.calls[0]["input"] == "analyze AAPL"
        assert runner.calls[0]["cwd"].endswith("ws")
        assert res.result == "wrote AAPL thesis"
        assert res.resumed is False
        assert sess.is_started()
        # repo root is injected on PYTHONPATH so `python -m src.agent.tools`
        # resolves even though cwd is the workspace
        from src.agent.session import _REPO_ROOT
        assert runner.calls[0]["env"]["PYTHONPATH"].startswith(str(_REPO_ROOT))

    def test_second_turn_resumes(self, tmp_path):
        runner = _FakeRunner(_ok_payload())
        sess = AgentSession(workspace=tmp_path / "ws", runner=runner)
        sess.run_turn("turn 1")
        res2 = sess.run_turn("turn 2")
        cmd2 = runner.calls[1]["cmd"]
        assert "--resume" in cmd2 and "--session-id" not in cmd2
        assert res2.resumed is True

    def test_model_override_per_turn(self, tmp_path):
        runner = _FakeRunner(_ok_payload())
        sess = AgentSession(workspace=tmp_path / "ws", runner=runner, model="sonnet")
        sess.run_turn("x", model="opus")
        cmd = runner.calls[0]["cmd"]
        assert cmd[cmd.index("--model") + 1] == "opus"  # per-turn override wins
        sess.run_turn("y")  # no override -> session default
        cmd2 = runner.calls[1]["cmd"]
        assert cmd2[cmd2.index("--model") + 1] == "sonnet"

    def test_session_date_uses_et_when_unpinned(self, tmp_path):
        from datetime import datetime
        from zoneinfo import ZoneInfo

        sess = AgentSession(workspace=tmp_path / "ws")  # no pinned date -> live ET
        et_today = datetime.now(ZoneInfo("US/Eastern")).date().isoformat()
        assert sess.session_date.isoformat() == et_today
        assert sess._state_file().name == f"{et_today}.json"

    def test_started_marker_persists_across_instances(self, tmp_path):
        ws = tmp_path / "ws"
        day = date(2026, 5, 27)
        AgentSession(workspace=ws, runner=_FakeRunner(_ok_payload()), session_date=day).run_turn("t1")
        # A fresh instance (e.g. next cron invocation) must see the started session.
        runner2 = _FakeRunner(_ok_payload())
        sess_b = AgentSession(workspace=ws, runner=runner2, session_date=day)
        assert sess_b.is_started()
        sess_b.run_turn("t2")
        assert "--resume" in runner2.calls[0]["cmd"]

    def test_session_id_stored_and_reused_within_day(self, tmp_path):
        ws = tmp_path / "ws"
        a = AgentSession(workspace=ws, runner=_FakeRunner(_ok_payload()), session_date=date(2026, 1, 1))
        assert a.session_id is None  # nothing created yet
        a.run_turn("t1")
        sid = a.session_id
        assert sid is not None
        uuid.UUID(sid)  # valid UUID generated on the first turn
        # a fresh instance the same day reuses the stored id (will resume it)
        b = AgentSession(workspace=ws, runner=_FakeRunner(_ok_payload()), session_date=date(2026, 1, 1))
        assert b.session_id == sid
        # a different day has no marker -> fresh
        c = AgentSession(workspace=ws, runner=_FakeRunner(_ok_payload()), session_date=date(2026, 1, 2))
        assert c.session_id is None

    def test_retries_fresh_on_session_id_collision(self, tmp_path):
        # Reproduces the real bug: no marker -> create with a fresh uuid, but the
        # CLI rejects it as already-in-use (a stale session); retry must succeed
        # with another fresh create.
        class _FlakyRunner:
            def __init__(self):
                self.calls = []

            def __call__(self, cmd, *, input, cwd, timeout, env=None):
                self.calls.append(cmd)
                if len(self.calls) == 1:
                    return SimpleNamespace(returncode=1, stdout="", stderr="Error: Session ID x is already in use.")
                return SimpleNamespace(returncode=0, stdout=_ok_payload(), stderr="")

        runner = _FlakyRunner()
        sess = AgentSession(workspace=tmp_path / "ws", runner=runner, session_date=date(2026, 1, 1))
        res = sess.run_turn("t")
        assert len(runner.calls) == 2  # collided once, retried
        assert "--session-id" in runner.calls[0] and "--session-id" in runner.calls[1]
        assert res.resumed is False
        assert sess.is_started()  # marker written with the fresh id

    def test_raises_on_error_payload(self, tmp_path):
        runner = _FakeRunner(json.dumps({"is_error": True, "result": "boom"}))
        sess = AgentSession(workspace=tmp_path / "ws", runner=runner)
        with pytest.raises(RuntimeError, match="boom"):
            sess.run_turn("x")
        assert not sess.is_started()  # a failed first turn must not mark started

    def test_raises_on_nonzero_exit(self, tmp_path):
        runner = _FakeRunner("", returncode=1, stderr="cli blew up")
        sess = AgentSession(workspace=tmp_path / "ws", runner=runner)
        with pytest.raises(RuntimeError, match="cli blew up"):
            sess.run_turn("x")


# --------------------------------------------------------------------------- #
# Turn prompts
# --------------------------------------------------------------------------- #
class TestPrompts:
    def test_morning_has_universe_held_and_discovery(self):
        p = prompts.morning_research_prompt(["AAPL", "MSFT"], held=["NVDA"])
        assert "Morning research" in p
        assert "AAPL" in p and "MSFT" in p
        assert "NVDA" in p
        assert "scoreboard" in p  # pure-LLM discovery via the scoreboard tool
        assert "advisory only" in p

    def test_intraday_includes_quotes(self):
        p = prompts.intraday_prompt(quotes={"AAPL": 300.0}, held=["AAPL"])
        assert "Intraday" in p
        assert "AAPL=300.0" in p

    def test_eod_mentions_lessons_and_grade(self):
        p = prompts.eod_review_prompt(["AAPL BUY"])
        assert "lessons.md" in p
        assert "AAPL BUY" in p


# --------------------------------------------------------------------------- #
# Orchestrator
# --------------------------------------------------------------------------- #
class _FakeSession:
    def __init__(self, journal, to_write=None):
        self.journal = journal
        self.model = "fake"
        self.prompts: list[str] = []
        self.models: list[str | None] = []
        self._to_write = to_write or []

    def run_turn(self, prompt, system_prompt=None, model=None):
        self.prompts.append(prompt)
        self.models.append(model)
        for d in self._to_write:
            self.journal.append_decision(d)
        return AgentTurnResult(result="ok", session_id="sid", resumed=False, raw={})


class TestFilterInUniverse:
    def test_split(self):
        ds = [Decision(symbol="AAPL", action="BUY"), Decision(symbol="ZZZZ", action="BUY")]
        kept, rejected = filter_in_universe(ds, ["AAPL", "MSFT"])
        assert [d.symbol for d in kept] == ["AAPL"]
        assert [d.symbol for d in rejected] == ["ZZZZ"]


class TestOrchestrator:
    def test_morning_runs_and_passes_prompt(self, tmp_path):
        sess = _FakeSession(Journal(root=tmp_path / "ws"))
        loop = AgentTradingLoop(session=sess, universe=["AAPL", "MSFT"])
        res = loop.run_morning_research()
        assert res.result == "ok"
        assert "Morning research" in sess.prompts[0]
        assert "AAPL" in sess.prompts[0]

    def test_research_uses_research_model_intraday_default(self, tmp_path):
        sess = _FakeSession(Journal(root=tmp_path / "ws"))
        loop = AgentTradingLoop(session=sess, universe=["AAPL"], research_model="opus")
        loop.run_morning_research()
        assert sess.models[-1] == "opus"   # deep research turn -> opus
        loop.run_intraday()
        assert sess.models[-1] is None     # intraday -> session default (sonnet)

    def test_out_of_universe_decision_is_flagged(self, tmp_path):
        sess = _FakeSession(
            Journal(root=tmp_path / "ws"),
            to_write=[Decision(symbol="AAPL", action="BUY"), Decision(symbol="ZZZZ", action="BUY")],
        )
        loop = AgentTradingLoop(session=sess, universe=["AAPL", "MSFT"])
        loop.run_intraday()
        assert len(loop.last_new_decisions) == 2
        assert [d.symbol for d in loop.last_kept] == ["AAPL"]
        assert [d.symbol for d in loop.last_rejected] == ["ZZZZ"]

    def test_held_from_portfolio_provider(self, tmp_path):
        j = Journal(root=tmp_path / "ws")
        j.init()

        class _PF:
            positions = {"NVDA": object(), "AMD": object()}

        loop = AgentTradingLoop(
            session=_FakeSession(j), universe=["NVDA", "AMD"], portfolio_provider=lambda: _PF()
        )
        assert loop.held_symbols() == ["AMD", "NVDA"]

    def test_held_falls_back_to_journal(self, tmp_path):
        j = Journal(root=tmp_path / "ws")
        j.init()
        j.write_position("AAPL", "# thesis")
        loop = AgentTradingLoop(session=_FakeSession(j), universe=["AAPL"])
        assert loop.held_symbols() == ["AAPL"]

    def test_eod_review_passes_outcomes_to_prompt(self, tmp_path):
        sess = _FakeSession(Journal(root=tmp_path / "ws"))
        loop = AgentTradingLoop(session=sess, universe=["AAPL"])
        loop.run_eod_review(outcomes=["AAPL BUY (stop 280) | now 300 | held 11@295 +1.7% | -> open"])
        assert "now 300 | held 11@295 +1.7%" in sess.prompts[0]
        assert "lessons.md" in sess.prompts[0]

    def test_schedule_registers_three_turns(self, tmp_path):
        loop = AgentTradingLoop(session=_FakeSession(Journal(root=tmp_path / "ws")), universe=["AAPL"])

        class _FakeScheduler:
            def __init__(self):
                self.jobs = []

            def add_market_open_job(self, func, job_id):
                self.jobs.append(job_id)

            def add_batch_job(self, func, interval_minutes, job_id):
                self.jobs.append((job_id, interval_minutes))

            def add_market_close_job(self, func, job_id):
                self.jobs.append(job_id)

        sch = _FakeScheduler()
        loop.schedule(sch, intraday_minutes=20)
        assert "agent_morning" in sch.jobs
        assert "agent_eod" in sch.jobs
        assert ("agent_intraday", 20) in sch.jobs


class TestRobustDecisionRead:
    def test_skips_malformed_line(self, tmp_path):
        j = Journal(root=tmp_path / "ws")
        j.decisions_file.parent.mkdir(parents=True, exist_ok=True)
        good = Decision(symbol="AAPL", action="BUY").model_dump_json()
        j.decisions_file.write_text(good + "\n{not valid json}\n" + good + "\n")
        assert len(j.read_decisions()) == 2  # malformed middle line skipped


# --------------------------------------------------------------------------- #
# Equity log
# --------------------------------------------------------------------------- #
class TestEquityLog:
    def _portfolio(self):
        from src.core.models import PortfolioState, Position
        return PortfolioState(
            cash=90000.0, equity=100000.0,
            positions={
                "AAPL": Position(symbol="AAPL", qty=10, avg_entry_price=300.0,
                                 current_price=310.0, unrealized_pnl=100.0, market_value=3100.0),
            },
        )

    def test_record_and_read(self, tmp_path):
        from src.agent.equity_log import record_equity, read_equity
        path = tmp_path / "equity.jsonl"
        snap = record_equity(self._portfolio(), path)
        assert snap["equity"] == 100000.0
        assert snap["cash"] == 90000.0
        assert snap["invested"] == 3100.0
        assert snap["open_pnl"] == 100.0
        assert snap["position_count"] == 1
        assert snap["positions"][0]["symbol"] == "AAPL"
        # appends, oldest first
        record_equity(self._portfolio(), path)
        records = read_equity(path)
        assert len(records) == 2
        assert records[0]["equity"] == 100000.0

    def test_read_missing_is_empty(self, tmp_path):
        from src.agent.equity_log import read_equity
        assert read_equity(tmp_path / "nope.jsonl") == []
