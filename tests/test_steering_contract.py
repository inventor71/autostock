"""F4 Phase 4 — cross-language steering contract (Python = authoritative side).

The console (operator-console, TS) mirrors this contract to write commands the daemon
reads. NL-only made this file-drop JSON the *only* console↔daemon coupling, so a silent
drift (a renamed verb/field) would have the daemon reject commands at runtime. This test
pins the live pydantic models to the committed golden `contract/contract.json`; the TS side
(`operator-console/test/contract.test.ts`) pins its runtime mirror to the same golden.

If a contract change is intentional, regenerate the golden:
    python tests/test_steering_contract.py --write
"""

from __future__ import annotations

import json
import sys
import typing
from pathlib import Path

# Allow `python tests/test_steering_contract.py --write` to run standalone (not just under
# pytest): put the repo root on sys.path before importing the daemon package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.agent.steering.records import (  # noqa: E402
    EventKind,
    SteeringCommand,
    SteeringEvent,
    SteeringVerb,
)

CONTRACT = Path(__file__).resolve().parents[1] / "operator-console" / "contract" / "contract.json"


def _compute() -> dict[str, list[str]]:
    """The contract derived from the LIVE pydantic models (single source of truth)."""
    return {
        "verbs": list(typing.get_args(SteeringVerb)),
        "event_kinds": list(typing.get_args(EventKind)),
        "command_fields": list(SteeringCommand.model_fields.keys()),
        "event_fields": list(SteeringEvent.model_fields.keys()),
    }


def test_committed_golden_matches_live_models():
    committed = json.loads(CONTRACT.read_text())
    assert committed == _compute(), (
        "steering contract drift: live pydantic models != committed contract.json. "
        "If intended, regenerate: `python tests/test_steering_contract.py --write` "
        "(and update operator-console/src/schema.ts to match)."
    )


def test_ts_shaped_command_validates_and_round_trips():
    # EXACTLY the shape operator-console FileDrop.build() emits onto the wire.
    wire = {
        "id": "0" * 32,
        "ts": "2026-05-30T12:00:00.000Z",
        "verb": "sell",
        "args": {"symbol": "AAPL", "size": 50, "unit": "%"},
        "confirmed": True,
        "token": "tok",
        "source": "human",
    }
    cmd = SteeringCommand.model_validate(wire)
    assert cmd.verb == "sell"
    assert cmd.confirmed is True
    assert cmd.source == "human"
    # the daemon-facing envelope round-trips with no field added/dropped
    assert set(cmd.model_dump(mode="json").keys()) == set(wire.keys())


def test_unconfirmed_command_is_accepted_but_flagged():
    # Fail-closed semantics live in the daemon (confirmed must be True to execute);
    # the model itself still parses an unconfirmed record.
    cmd = SteeringCommand.model_validate(
        {"verb": "buy", "args": {}, "confirmed": False, "token": "", "source": "human"}
    )
    assert cmd.confirmed is False


def test_ts_shaped_event_envelope_parses():
    wire = {
        "id": "a" * 32,
        "corr_id": None,
        "ts": "2026-05-30T12:00:00Z",
        "kind": "outcome",
        "payload": {"outcome": "filled", "detail": "SELL 50% AAPL"},
    }
    ev = SteeringEvent.model_validate(wire)
    assert ev.kind == "outcome"
    assert ev.corr_id is None


if __name__ == "__main__":
    import sys

    if "--write" in sys.argv:
        CONTRACT.parent.mkdir(parents=True, exist_ok=True)
        CONTRACT.write_text(json.dumps(_compute(), indent=2) + "\n")
        print("wrote", CONTRACT)
    else:
        print("current contract:", json.dumps(_compute(), indent=2))
