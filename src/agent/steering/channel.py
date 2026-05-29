"""SteeringChannel: the file-drop boundary between the operator tool and the daemon.

- ``commands.jsonl``  (operator -> daemon): read torn-safely, validate
  ``confirmed`` + ``token`` (BR-1'/BR-10.2), dedup by id (BR-11.2), reject the
  rest fail-closed with an outcome event.
- ``events.jsonl``    (daemon -> operator): append-only outcomes/fills/pending/...
- ``snapshot.json``   (daemon -> operator): atomic live read view (BR-12.1).

The command file is low-volume (a day of human commands), so it is re-scanned
from the top each poll and de-duplicated by a persisted, day-scoped processed-id
set -- simpler and safer for the order path than a byte cursor (a crash can only
cause at-least-once, never a silently-dropped human command). The token is
validated in constant time and NEVER written to events/logs (SECURITY-03).
"""

from __future__ import annotations

import hmac
import json
from datetime import datetime
from pathlib import Path

from loguru import logger

from src.agent.steering.jsonl import atomic_write_text, read_complete_lines
from src.agent.steering.records import SteeringCommand, SteeringEvent
from src.agent.steering.state import today_et


class SteeringChannel:
    def __init__(self, steering_dir: str | Path, token: str):
        self.dir = Path(steering_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.commands_file = self.dir / "commands.jsonl"
        self.events_file = self.dir / "events.jsonl"
        self.snapshot_file = self.dir / "snapshot.json"
        self._processed_file = self.dir / ".processed.json"
        self._token = token
        self._processed: set[str] = set()
        self._load_processed()

    # ---- processed-id dedup (day-scoped, persisted) ----------------------- #
    def _load_processed(self) -> None:
        try:
            raw = json.loads(self._processed_file.read_text(encoding="utf-8"))
            if raw.get("date") == today_et().isoformat():
                self._processed = set(raw.get("ids", []))
        except (FileNotFoundError, ValueError):
            self._processed = set()

    def _persist_processed(self) -> None:
        atomic_write_text(
            self._processed_file,
            json.dumps({"date": today_et().isoformat(), "ids": sorted(self._processed)}),
        )

    def mark_processed(self, command_id: str) -> None:
        """Called by the worker AFTER handling a command, so a re-read skips it."""
        self._processed.add(command_id)
        self._persist_processed()

    # ---- commands in ------------------------------------------------------ #
    def read_new_commands(self) -> list[SteeringCommand]:
        """Return validated, not-yet-processed commands. Rejects unconfirmed /
        bad-token / malformed lines fail-closed (emitting a rejection outcome)."""
        lines, _ = read_complete_lines(self.commands_file, 0)
        valid: list[SteeringCommand] = []
        for line in lines:
            try:
                cmd = SteeringCommand.model_validate_json(line)
            except Exception as exc:
                logger.warning("steering: skipping unparseable command line: {}", exc)
                continue
            if cmd.id in self._processed:
                continue
            ok, reason = self._validate(cmd)
            if not ok:
                logger.warning("steering: rejected {} command (id={}): {}", cmd.verb, cmd.id, reason)
                self.emit_outcome(cmd.id, "rejected", reason)
                self.mark_processed(cmd.id)  # don't re-reject every poll
                continue
            valid.append(cmd)
        return valid

    def _validate(self, cmd: SteeringCommand) -> tuple[bool, str]:
        if cmd.confirmed is not True:
            return False, "unconfirmed"  # daemon never confirms (BR-1')
        # constant-time compare; the token value is never logged (SECURITY-03)
        if not self._token or not hmac.compare_digest(cmd.token or "", self._token):
            return False, "bad token"
        return True, ""

    # ---- events / snapshot out ------------------------------------------- #
    def append_event(self, event: SteeringEvent) -> None:
        self.events_file.parent.mkdir(parents=True, exist_ok=True)
        with self.events_file.open("a", encoding="utf-8") as fh:
            fh.write(event.model_dump_json() + "\n")

    def emit_outcome(self, corr_id: str, outcome: str, detail: str = "") -> None:
        self.append_event(
            SteeringEvent(corr_id=corr_id, kind="outcome",
                          payload={"outcome": outcome, "detail": detail})
        )

    def publish_snapshot(self, snapshot: dict) -> None:
        """Atomically publish the live read view (no torn JSON for the reader)."""
        payload = {**snapshot, "published_at": datetime.now().isoformat()}
        atomic_write_text(self.snapshot_file, json.dumps(payload))
