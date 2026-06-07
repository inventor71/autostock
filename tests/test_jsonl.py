"""Unit tests for src/core/jsonl.py read-all/append helpers (R4)."""
from __future__ import annotations

from pydantic import BaseModel

from src.core.jsonl import (
    append_record,
    append_records,
    read_records,
)


class _Rec(BaseModel):
    a: int
    b: str


def test_read_missing_file_returns_empty(tmp_path):
    assert read_records(tmp_path / "nope.jsonl") == []


def test_read_dict_round_trip(tmp_path):
    p = tmp_path / "x.jsonl"
    append_record(p, {"a": 1, "b": "hi"})
    append_record(p, {"a": 2, "b": "yo"})
    assert read_records(p) == [{"a": 1, "b": "hi"}, {"a": 2, "b": "yo"}]


def test_append_creates_parent_dirs(tmp_path):
    p = tmp_path / "deep" / "nested" / "x.jsonl"
    append_record(p, {"a": 1, "b": "z"})
    assert p.exists() and read_records(p) == [{"a": 1, "b": "z"}]


def test_blank_lines_skipped(tmp_path):
    p = tmp_path / "x.jsonl"
    p.write_text('{"a": 1, "b": "x"}\n\n   \n{"a": 2, "b": "y"}\n', encoding="utf-8")
    assert read_records(p) == [{"a": 1, "b": "x"}, {"a": 2, "b": "y"}]


def test_corrupt_line_skipped(tmp_path):
    p = tmp_path / "x.jsonl"
    p.write_text('{"a": 1, "b": "x"}\nNOT JSON\n{"a": 2, "b": "y"}\n', encoding="utf-8")
    assert read_records(p) == [{"a": 1, "b": "x"}, {"a": 2, "b": "y"}]


def test_torn_last_line_dropped(tmp_path):
    p = tmp_path / "x.jsonl"
    p.write_text('{"a": 1, "b": "x"}\n{"a": 2, "b":', encoding="utf-8")  # torn, no newline
    assert read_records(p) == [{"a": 1, "b": "x"}]


def test_model_parsing(tmp_path):
    p = tmp_path / "x.jsonl"
    append_records(p, [_Rec(a=1, b="x"), _Rec(a=2, b="y")])
    got = read_records(p, _Rec)
    assert got == [_Rec(a=1, b="x"), _Rec(a=2, b="y")]
    assert all(isinstance(r, _Rec) for r in got)


def test_model_invalid_line_skipped(tmp_path):
    p = tmp_path / "x.jsonl"
    p.write_text('{"a": 1, "b": "ok"}\n{"a": "not-int", "b": 3}\n', encoding="utf-8")
    got = read_records(p, _Rec)
    assert got == [_Rec(a=1, b="ok")]


def test_append_records_empty_noop(tmp_path):
    p = tmp_path / "x.jsonl"
    append_records(p, [])
    assert not p.exists()


def test_append_record_pydantic(tmp_path):
    p = tmp_path / "x.jsonl"
    append_record(p, _Rec(a=7, b="m"))
    assert read_records(p, _Rec) == [_Rec(a=7, b="m")]
