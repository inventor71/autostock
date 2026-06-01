"""F22: Decision.turn_id backward compatibility."""
from src.agent.journal import Decision


def test_decision_default_turn_id_is_none():
    d = Decision(symbol="AAPL", action="BUY")
    assert d.turn_id is None


def test_decision_with_turn_id():
    d = Decision(symbol="AAPL", action="BUY", turn_id="R1")
    assert d.turn_id == "R1"


def test_decision_parse_without_turn_id():
    raw = '{"symbol": "AAPL", "action": "BUY", "confidence": 0.5}'
    d = Decision.model_validate_json(raw)
    assert d.turn_id is None


def test_decision_parse_with_turn_id():
    raw = '{"symbol": "AAPL", "action": "BUY", "turn_id": "I3", "confidence": 0.5}'
    d = Decision.model_validate_json(raw)
    assert d.turn_id == "I3"


def test_decision_serialization_includes_turn_id():
    d = Decision(symbol="AAPL", action="BUY", turn_id="W1")
    data = d.model_dump()
    assert data["turn_id"] == "W1"
