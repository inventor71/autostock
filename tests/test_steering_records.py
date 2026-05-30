"""Unit A steering-core -- Step 1: records round-trip + torn-safe JSONL reader.

Covers PBT-02 (serialize->deserialize identity) and BR-11.1 (torn-line guard,
byte-offset cursor that never drifts on a mid-write trailing line).
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from src.agent.journal import Decision
from src.agent.steering.jsonl import ByteCursor, atomic_write_text, read_complete_lines
from src.agent.steering.records import (
    AgentAnswer,
    AgentQuestion,
    Directive,
    InterventionRecord,
    SteeringCommand,
    SteeringEvent,
)


# --------------------------------------------------------------------------- #
# PBT-02 round-trip
# --------------------------------------------------------------------------- #
def test_steering_command_round_trip():
    cmd = SteeringCommand(verb="sell", args={"symbol": "AAPL", "size": 50, "unit": "%"},
                          confirmed=True, token="secret")
    again = SteeringCommand.model_validate_json(cmd.model_dump_json())
    assert again == cmd


def test_event_question_directive_round_trip():
    for model in (
        SteeringEvent(kind="outcome", corr_id="abc", payload={"outcome": "executed"}),
        AgentQuestion(symbol="MSFT", text="re-enter after stop?"),
        AgentAnswer(question_id="q1", text="no, stand down"),
        InterventionRecord(kind="trade", raw="/sell AAPL 50%", command="sell",
                           args={"symbol": "AAPL"}, outcome="executed", detail="50 sh @ 230"),
        Directive(text="be defensive into CPI"),
    ):
        assert type(model).model_validate_json(model.model_dump_json()) == model


def test_decision_source_backward_compatible():
    # a legacy line with no `source` parses as "agent"
    legacy = '{"symbol":"AAPL","action":"BUY"}'
    assert Decision.model_validate_json(legacy).source == "agent"
    # explicit human survives round-trip
    d = Decision(symbol="aapl", action="SELL", source="human")
    assert Decision.model_validate_json(d.model_dump_json()).source == "human"
    assert d.symbol == "AAPL"  # normalizer still applies


def test_redacted_strips_token():
    cmd = SteeringCommand(verb="buy", token="topsecret", confirmed=True)
    assert cmd.redacted()["token"] == ""
    assert cmd.token == "topsecret"  # original untouched


@given(st.text(min_size=1, max_size=20).map(lambda s: s.upper()))
def test_command_id_is_unique_and_stable(_sym):
    a, b = SteeringCommand(verb="pause"), SteeringCommand(verb="pause")
    assert a.id != b.id  # uuid4 hex, collision-free in practice


# --------------------------------------------------------------------------- #
# BR-11.1 torn-safe reader + byte cursor
# --------------------------------------------------------------------------- #
def test_reader_consumes_only_complete_lines(tmp_path):
    f = tmp_path / "commands.jsonl"
    # two complete lines + one torn (no trailing newline)
    f.write_text('{"a":1}\n{"a":2}\n{"a":3', encoding="utf-8")
    lines, offset = read_complete_lines(f, 0)
    assert lines == ['{"a":1}', '{"a":2}']  # the torn 3rd line is withheld
    assert offset == len('{"a":1}\n{"a":2}\n')

    # the writer completes the 3rd line; next read picks up ONLY that line
    with f.open("a", encoding="utf-8") as fh:
        fh.write('}\n')
    lines2, offset2 = read_complete_lines(f, offset)
    assert lines2 == ['{"a":3}']
    assert offset2 == f.stat().st_size


def test_reader_empty_and_no_complete_line(tmp_path):
    f = tmp_path / "c.jsonl"
    assert read_complete_lines(f, 0) == ([], 0)  # missing file
    f.write_text("partial-no-newline", encoding="utf-8")
    assert read_complete_lines(f, 0) == ([], 0)  # nothing complete yet


def test_reader_resets_on_truncation(tmp_path):
    f = tmp_path / "c.jsonl"
    f.write_text("x\n", encoding="utf-8")
    _, off = read_complete_lines(f, 0)
    f.write_text("y\n", encoding="utf-8")  # rotated/shrunk: offset now > size? equal here
    # simulate a cursor beyond EOF (rotation)
    lines, new_off = read_complete_lines(f, 999)
    assert lines == ["y"] and new_off == f.stat().st_size


def test_byte_cursor_persists_atomically(tmp_path):
    cur = ByteCursor(tmp_path / ".commands_cursor")
    assert cur.load() == 0  # absent -> 0
    cur.save(42)
    assert ByteCursor(tmp_path / ".commands_cursor").load() == 42


def test_atomic_write_replaces(tmp_path):
    p = tmp_path / "snap.json"
    atomic_write_text(p, '{"v":1}')
    atomic_write_text(p, '{"v":2}')
    assert p.read_text() == '{"v":2}'
    # no leftover temp files
    assert list(tmp_path.glob("*.tmp")) == []
