"""U1 — TriggerSpec/SourceRef/Verdict model behavior (example-based)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from src.agent.triggers.models import SourceRef, TriggerSpec, Verdict


def _future(days: int = 7) -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=days)


# ---- Verdict ---------------------------------------------------------------- #

def test_verdict_accepts_real_bool():
    assert Verdict(fire=True, why="x").fire is True
    assert Verdict(fire=False).fire is False


@pytest.mark.parametrize("bad", ["true", 1, 0, [], None])
def test_verdict_rejects_non_bool_fire(bad):
    # Fail-closed: a malformed 'fire' must not coerce to a truthy fire.
    with pytest.raises(ValidationError):
        Verdict(fire=bad)


def test_verdict_why_is_capped():
    v = Verdict(fire=True, why="z" * 5000)
    assert len(v.why) <= 500
    assert v.why.endswith("…")


# ---- SourceRef -------------------------------------------------------------- #

def test_signal_source_requires_known_name():
    s = SourceRef(kind="signal", name="macro")
    assert s.ctx_key() == "macro"
    with pytest.raises(ValidationError):
        SourceRef(kind="signal", name="not_a_signal")
    with pytest.raises(ValidationError):
        SourceRef(kind="signal")  # missing name


def test_signal_source_rejects_url():
    with pytest.raises(ValidationError):
        SourceRef(kind="signal", name="macro", url="https://x.com")


def test_webfetch_requires_absolute_url():
    s = SourceRef(kind="webfetch", url="https://fred.stlouisfed.org/series/VIX")
    assert s.ctx_key().startswith("fetch_fred_stlouisfed_org")
    with pytest.raises(ValidationError):
        SourceRef(kind="webfetch", url="not-a-url")
    with pytest.raises(ValidationError):
        SourceRef(kind="webfetch")  # missing url


def test_webfetch_rejects_name():
    with pytest.raises(ValidationError):
        SourceRef(kind="webfetch", url="https://x.com", name="macro")


def test_source_key_override():
    s = SourceRef(kind="signal", name="macro", key="vix_block")
    assert s.ctx_key() == "vix_block"


def test_websearch_kind_is_not_allowed():
    # websearch is a follow-up (no search API in first cut) — not a valid kind.
    with pytest.raises(ValidationError):
        SourceRef(kind="websearch", name="vix")


# ---- TriggerSpec ------------------------------------------------------------ #

def test_spec_minimal_ok():
    spec = TriggerSpec(id="vix-spike", thesis="VIX regime shift", cadence="hourly", expires=_future())
    assert spec.wake_symbol() == "MACRO"
    assert spec.entry_inducing is True
    assert not spec.is_expired()


def test_spec_primary_symbol_uppercased():
    spec = TriggerSpec(id="t1", thesis="x", cadence="daily", expires=_future(), primary_symbol="aapl")
    assert spec.primary_symbol == "AAPL"
    assert spec.wake_symbol() == "AAPL"


@pytest.mark.parametrize("bad_id", ["UPPER", "has space", "-leading", "x" * 65, "", "sym/../etc"])
def test_spec_rejects_bad_id(bad_id):
    with pytest.raises(ValidationError):
        TriggerSpec(id=bad_id, thesis="x", cadence="hourly", expires=_future())


def test_spec_rejects_empty_thesis():
    with pytest.raises(ValidationError):
        TriggerSpec(id="t1", thesis="   ", cadence="hourly", expires=_future())


def test_spec_expiry_with_naive_datetime_is_normalized():
    naive = datetime.now() + timedelta(days=1)  # local-naive on purpose (tests normalization)
    spec = TriggerSpec(id="t1", thesis="x", cadence="hourly", expires=naive)
    assert spec.expires.tzinfo is not None
    assert not spec.is_expired()


def test_spec_is_expired_past():
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    spec = TriggerSpec(id="t1", thesis="x", cadence="hourly", expires=past)
    assert spec.is_expired()
