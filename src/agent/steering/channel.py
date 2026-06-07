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

from src.core.markettime import et_today
from src.agent.steering.jsonl import atomic_write_text, read_complete_lines
from src.agent.steering.records import SteeringCommand, SteeringEvent


class SteeringChannel:
    def __init__(self, steering_dir: str | Path, token: str):
        self.dir = Path(steering_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.commands_file = self.dir / "commands.jsonl"
        self.events_file = self.dir / "events.jsonl"
        self.snapshot_file = self.dir / "snapshot.json"
        self.codebase_file = self.dir / "codebase.json"  # F29
        self._processed_file = self.dir / ".processed.json"
        self._token = token
        self._processed: set[str] = set()
        self._load_processed()

    # ---- processed-id dedup (day-scoped, persisted) ----------------------- #
    def _load_processed(self) -> None:
        try:
            raw = json.loads(self._processed_file.read_text(encoding="utf-8"))
            if raw.get("date") == et_today().isoformat():
                self._processed = set(raw.get("ids", []))
        except (FileNotFoundError, ValueError):
            self._processed = set()

    def _persist_processed(self) -> None:
        atomic_write_text(
            self._processed_file,
            json.dumps({"date": et_today().isoformat(), "ids": sorted(self._processed)}),
        )

    def mark_processed(self, command_id: str) -> None:
        """Called by the worker AFTER handling a command, so a re-read skips it."""
        self._processed.add(command_id)
        self._persist_processed()

    def daily_reset(self) -> None:
        """Re-scope the processed-id set to today and archive the day's command
        file, so neither grows unbounded across a multi-day daemon (critic #4).
        Called by the ET-midnight sweep job. Idempotent."""
        self._processed = set()
        self._persist_processed()
        if self.commands_file.exists() and self.commands_file.stat().st_size > 0:
            archive = self.commands_file.with_suffix(
                f".jsonl.{et_today().isoformat()}.archived"
            )
            try:
                self.commands_file.replace(archive)  # atomic rename; operator appends create a fresh file
            except OSError as exc:
                logger.warning("steering: could not archive commands file: {}", exc)

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

    # ---- off-hours human-trade queue (BR-2.7) ---------------------------- #
    @property
    def _offhours_file(self):
        return self.dir / "pending_human_trades.jsonl"

    def queue_offhours(self, cmd: SteeringCommand) -> None:
        """Park a human trade issued while the market is closed; the market-open
        job drains it (BR-2.7). Stored token-redacted (it was already validated)."""
        with self._offhours_file.open("a", encoding="utf-8") as fh:
            fh.write(SteeringCommand.model_validate(cmd.redacted()).model_dump_json() + "\n")

    def drain_offhours(self) -> list[SteeringCommand]:
        """Return all queued off-hours trades and clear the queue (atomic clear)."""
        if not self._offhours_file.exists():
            return []
        out: list[SteeringCommand] = []
        for line in self._offhours_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(SteeringCommand.model_validate_json(line))
            except Exception as exc:
                logger.warning("steering: bad off-hours line skipped: {}", exc)
        self._offhours_file.unlink(missing_ok=True)
        return out

    def list_offhours(self) -> list[SteeringCommand]:
        """Read the queued off-hours trades WITHOUT clearing (for the snapshot so the
        operator can see -- and cancel -- what will fire at the next open)."""
        if not self._offhours_file.exists():
            return []
        out: list[SteeringCommand] = []
        for line in self._offhours_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(SteeringCommand.model_validate_json(line))
            except Exception as exc:
                logger.warning("steering: bad off-hours line skipped: {}", exc)
        return out

    def remove_offhours(self, command_id: str) -> bool:
        """Drop one queued off-hours trade by id (operator cancel of a deferred trade).
        Rewrites the queue minus that id; returns whether anything was removed. Runs on
        the CommandBus worker (same thread as queue/drain), so no file race."""
        current = self.list_offhours()
        remaining = [c for c in current if c.id != command_id]
        if len(remaining) == len(current):
            return False
        if remaining:
            self._offhours_file.write_text(
                "".join(c.model_dump_json() + "\n" for c in remaining), encoding="utf-8")
        else:
            self._offhours_file.unlink(missing_ok=True)
        return True

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

    # F29: codebase tree for supervisor orientation --------------------------- #
    def publish_codebase(self, tree_text: str) -> None:
        """Publish the project directory tree as ``codebase.json`` so the operator
        agent can discover the repo structure via ``steer_read{command:/codebase}``."""
        payload = {"tree": tree_text, "published_at": datetime.now().isoformat()}
        atomic_write_text(self.codebase_file, json.dumps(payload))
