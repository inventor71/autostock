"""U1 — property-based tests (PBT-02 round-trip, PBT-03 invariant).

Partial PBT mode (F88 state.md): PBT-02/03/07/08 apply here. Domain generators
(PBT-07) build structurally-valid specs; Hypothesis shrinks + logs the seed on
failure (PBT-08, default config).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from hypothesis import given
from hypothesis import strategies as st

from src.agent.triggers.models import SIGNAL_NAMES, SourceRef, TriggerSpec, Verdict

# ---- domain generators (PBT-07) -------------------------------------------- #

_ids = st.from_regex(r"[a-z0-9][a-z0-9-]{0,40}", fullmatch=True)
_theses = st.text(min_size=1, max_size=200).map(lambda s: s.strip() or "thesis").filter(lambda s: s.strip())
_cadence = st.sampled_from(["hourly", "daily"])
_aware_future = st.integers(min_value=1, max_value=3650).map(
    lambda d: datetime.now(timezone.utc) + timedelta(days=d)
)

_signal_sources = st.sampled_from(sorted(SIGNAL_NAMES)).map(
    lambda n: SourceRef(kind="signal", name=n)
)
_webfetch_sources = st.from_regex(r"[a-z0-9]{1,12}", fullmatch=True).map(
    lambda h: SourceRef(kind="webfetch", url=f"https://{h}.example.com/data")
)
_sources = st.lists(st.one_of(_signal_sources, _webfetch_sources), max_size=5)


@st.composite
def specs(draw):
    return TriggerSpec(
        id=draw(_ids),
        thesis=draw(_theses),
        cadence=draw(_cadence),
        expires=draw(_aware_future),
        sources=draw(_sources),
        primary_symbol=draw(st.none() | st.from_regex(r"[A-Z]{1,5}", fullmatch=True)),
        entry_inducing=draw(st.booleans()),
    )


# ---- PBT-02: serialize → parse round-trip ---------------------------------- #

@given(specs())
def test_spec_json_roundtrip(spec):
    restored = TriggerSpec.model_validate_json(spec.model_dump_json())
    assert restored == spec


@given(st.booleans(), st.text(max_size=50))
def test_verdict_roundtrip(fire, why):
    v = Verdict(fire=fire, why=why)
    restored = Verdict.model_validate_json(v.model_dump_json())
    assert restored == v


# ---- PBT-03: invariants ----------------------------------------------------- #

@given(specs())
def test_future_spec_never_expired_now(spec):
    # Every generated spec has a strictly-future expiry → never expired "now".
    assert not spec.is_expired()


@given(specs(), st.integers(min_value=1, max_value=10_000))
def test_expiry_monotone_in_time(spec, days_past_expiry):
    # Evaluated far enough past its expiry, a spec is always expired (TTL invariant).
    later = spec.expires + timedelta(days=days_past_expiry)
    assert spec.is_expired(now=later)


@given(specs())
def test_wake_symbol_never_empty(spec):
    assert spec.wake_symbol()  # "MACRO" fallback or the uppercased primary symbol
