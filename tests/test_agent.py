import json
import uuid
from datetime import date, datetime
from types import SimpleNamespace

import pandas as pd
import pytest
from pydantic import ValidationError

from src.agent.journal import Decision, Journal
from src.agent.session import AgentSession
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

    def __call__(self, cmd, *, input, cwd, timeout):
        self.calls.append({"cmd": cmd, "input": input, "cwd": cwd, "timeout": timeout})
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

    def test_second_turn_resumes(self, tmp_path):
        runner = _FakeRunner(_ok_payload())
        sess = AgentSession(workspace=tmp_path / "ws", runner=runner)
        sess.run_turn("turn 1")
        res2 = sess.run_turn("turn 2")
        cmd2 = runner.calls[1]["cmd"]
        assert "--resume" in cmd2 and "--session-id" not in cmd2
        assert res2.resumed is True

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

    def test_session_id_deterministic_per_day(self, tmp_path):
        a = AgentSession(workspace=tmp_path / "ws", session_date=date(2026, 1, 1))
        b = AgentSession(workspace=tmp_path / "ws2", session_date=date(2026, 1, 1))
        c = AgentSession(workspace=tmp_path / "ws3", session_date=date(2026, 1, 2))
        assert a.session_id == b.session_id  # same day -> same id
        assert a.session_id != c.session_id  # new day -> fresh id
        uuid.UUID(a.session_id)  # valid UUID

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
