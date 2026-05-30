"""Unit A steering-core -- Step 3: SteeringChannel (file-drop in/out + snapshot)."""

from __future__ import annotations

import json

from src.agent.steering.channel import SteeringChannel
from src.agent.steering.records import SteeringCommand, SteeringEvent

TOKEN = "op-secret-token"


def _append(path, cmd: SteeringCommand):
    with path.open("a", encoding="utf-8") as fh:
        fh.write(cmd.model_dump_json() + "\n")


def test_valid_command_returned(tmp_path):
    ch = SteeringChannel(tmp_path, TOKEN)
    cmd = SteeringCommand(verb="pause", confirmed=True, token=TOKEN)
    _append(ch.commands_file, cmd)
    got = ch.read_new_commands()
    assert [c.id for c in got] == [cmd.id]


def test_unconfirmed_rejected_failclosed(tmp_path):
    ch = SteeringChannel(tmp_path, TOKEN)
    cmd = SteeringCommand(verb="kill", confirmed=False, token=TOKEN)
    _append(ch.commands_file, cmd)
    assert ch.read_new_commands() == []
    events = ch.events_file.read_text().splitlines()
    ev = SteeringEvent.model_validate_json(events[-1])
    assert ev.corr_id == cmd.id and ev.payload["outcome"] == "rejected"
    assert ev.payload["detail"] == "unconfirmed"


def test_bad_token_rejected_and_not_logged(tmp_path):
    ch = SteeringChannel(tmp_path, TOKEN)
    cmd = SteeringCommand(verb="buy", confirmed=True, token="WRONG")
    _append(ch.commands_file, cmd)
    assert ch.read_new_commands() == []
    blob = ch.events_file.read_text()
    assert "bad token" in blob
    assert "WRONG" not in blob  # token value never echoed (SECURITY-03)


def test_processed_dedup_across_polls(tmp_path):
    ch = SteeringChannel(tmp_path, TOKEN)
    cmd = SteeringCommand(verb="resume", confirmed=True, token=TOKEN)
    _append(ch.commands_file, cmd)
    got = ch.read_new_commands()
    assert len(got) == 1
    ch.mark_processed(got[0].id)
    assert ch.read_new_commands() == []  # not re-returned


def test_processed_persists_across_restart(tmp_path):
    ch = SteeringChannel(tmp_path, TOKEN)
    cmd = SteeringCommand(verb="resume", confirmed=True, token=TOKEN)
    _append(ch.commands_file, cmd)
    ch.mark_processed(ch.read_new_commands()[0].id)
    ch2 = SteeringChannel(tmp_path, TOKEN)  # restart
    assert ch2.read_new_commands() == []  # still deduped (persisted)


def test_torn_last_line_withheld(tmp_path):
    ch = SteeringChannel(tmp_path, TOKEN)
    good = SteeringCommand(verb="pause", confirmed=True, token=TOKEN)
    ch.commands_file.write_text(good.model_dump_json() + "\n" + '{"verb":"kill","conf',
                                encoding="utf-8")
    got = ch.read_new_commands()
    assert [c.id for c in got] == [good.id]  # torn 2nd line ignored until complete


def test_snapshot_atomic_and_complete(tmp_path):
    ch = SteeringChannel(tmp_path, TOKEN)
    ch.publish_snapshot({"run_state": {"paused": False}, "positions": []})
    data = json.loads(ch.snapshot_file.read_text())
    assert data["run_state"]["paused"] is False
    assert "published_at" in data
    assert list(tmp_path.glob("*.tmp")) == []
