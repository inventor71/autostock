"""TriggerStore — durable CRUD for agent-authored long-horizon triggers (FR-3).

Layout (one directory per trigger, under the gitignored workspace):

    workspace/triggers/<id>/
        spec.json      canonical TriggerSpec (machine round-trip target, PBT-02)
        predicate.py   agent-authored should_fire(ctx) source (untrusted)
        state.json     daemon-managed TriggerState (the agent never writes this)
        trigger.md     rendered human view (generated from spec; never parsed back)

Single writer per file is the daemon (control plane); the agent only ever mutates
triggers through the MCP server, never by hand-editing files. Writes go through
``atomic_write_text`` (temp + ``os.replace``) so a concurrent read never sees a torn
file — same primitive the journal/decisions log use.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

from src.agent.journal import DEFAULT_ROOT
from src.agent.steering.jsonl import atomic_write_text
from src.agent.triggers.ast_screen import AstScreen, AstViolation
from src.agent.triggers.models import (
    TriggerDetail,
    TriggerSpec,
    TriggerState,
    TriggerSummary,
)

# Hard cap on predicate source size (SECURITY-05): a predicate is a small pure
# function, not a program. Bounds both the AST screen and what we mount into the
# sandbox.
PREDICATE_MAX_BYTES = 16_384
# Ceiling on simultaneously-registered triggers (FR-9, runaway/cost guard). The
# evaluator/config may impose a lower active limit; this is the store's backstop.
MAX_TRIGGERS = 64


class TriggerError(ValueError):
    """Registration/validation failure surfaced back to the agent via MCP."""

    def __init__(self, message: str, violations: list[AstViolation] | None = None):
        super().__init__(message)
        self.violations = violations or []


class TriggerStore:
    def __init__(self, root: str | Path | None = None, *, screen: AstScreen | None = None):
        # ``root`` is the triggers dir itself; default = <workspace>/triggers.
        self.root = Path(root) if root else (DEFAULT_ROOT / "triggers")
        self._screen = screen or AstScreen()

    # ---- paths -------------------------------------------------------------- #
    def _dir(self, trigger_id: str) -> Path:
        return self.root / trigger_id

    def exists(self, trigger_id: str) -> bool:
        return (self._dir(trigger_id) / "spec.json").is_file()

    # ---- create ------------------------------------------------------------- #
    def register(self, spec: TriggerSpec, predicate_src: str) -> TriggerSpec:
        """Validate + persist a new trigger. Raises ``TriggerError`` on rejection.

        Registration is create-only: re-registering an existing id is an error
        (cancel first) so a live trigger's state.json is never silently reset.
        """
        if self.exists(spec.id):
            raise TriggerError(f"trigger id {spec.id!r} already exists (cancel it first)")

        if spec.is_expired():
            raise TriggerError("trigger 'expires' is already in the past")

        encoded = predicate_src.encode("utf-8")
        if len(encoded) > PREDICATE_MAX_BYTES:
            raise TriggerError(
                f"predicate source {len(encoded)}B exceeds {PREDICATE_MAX_BYTES}B limit"
            )

        violations = self._screen.check(predicate_src)
        if violations:
            raise TriggerError(
                "predicate rejected by static screen: "
                + "; ".join(str(v) for v in violations),
                violations=violations,
            )

        active = self.count()
        if active >= MAX_TRIGGERS:
            raise TriggerError(f"too many active triggers ({active}/{MAX_TRIGGERS}); cancel some first")

        d = self._dir(spec.id)
        d.mkdir(parents=True, exist_ok=True)
        atomic_write_text(d / "spec.json", spec.model_dump_json(indent=2))
        atomic_write_text(d / "predicate.py", predicate_src)
        atomic_write_text(d / "state.json", TriggerState().model_dump_json(indent=2))
        atomic_write_text(d / "trigger.md", self._render_md(spec))
        return spec

    # ---- read --------------------------------------------------------------- #
    def ids(self) -> list[str]:
        if not self.root.is_dir():
            return []
        return sorted(
            p.name for p in self.root.iterdir()
            if p.is_dir() and (p / "spec.json").is_file()
        )

    def count(self) -> int:
        return len(self.ids())

    def load_spec(self, trigger_id: str) -> TriggerSpec:
        path = self._dir(trigger_id) / "spec.json"
        if not path.is_file():
            raise TriggerError(f"no such trigger: {trigger_id!r}")
        return TriggerSpec.model_validate_json(path.read_text())

    def load_state(self, trigger_id: str) -> TriggerState:
        path = self._dir(trigger_id) / "state.json"
        if not path.is_file():
            return TriggerState()
        return TriggerState.model_validate_json(path.read_text())

    def load_predicate(self, trigger_id: str) -> str:
        path = self._dir(trigger_id) / "predicate.py"
        if not path.is_file():
            raise TriggerError(f"no such trigger: {trigger_id!r}")
        return path.read_text()

    def list(self) -> list[TriggerSummary]:
        out: list[TriggerSummary] = []
        for tid in self.ids():
            spec = self.load_spec(tid)
            state = self.load_state(tid)
            out.append(TriggerSummary(
                id=spec.id, thesis=spec.thesis, cadence=spec.cadence,
                expires=spec.expires, disabled=state.disabled, fired_count=state.fired_count,
            ))
        return out

    def inspect(self, trigger_id: str) -> TriggerDetail:
        return TriggerDetail(
            spec=self.load_spec(trigger_id),
            state=self.load_state(trigger_id),
            predicate_src=self.load_predicate(trigger_id),
        )

    def active_specs(self, now: datetime | None = None) -> list[TriggerSpec]:
        """Specs eligible for evaluation: not expired and not disabled (FR-9)."""
        out: list[TriggerSpec] = []
        for tid in self.ids():
            spec = self.load_spec(tid)
            if spec.is_expired(now):
                continue
            if self.load_state(tid).disabled:
                continue
            out.append(spec)
        return out

    # ---- update / delete ---------------------------------------------------- #
    def update_state(self, trigger_id: str, state: TriggerState) -> None:
        """Persist daemon-managed state (single writer = daemon)."""
        d = self._dir(trigger_id)
        if not (d / "spec.json").is_file():
            raise TriggerError(f"no such trigger: {trigger_id!r}")
        atomic_write_text(d / "state.json", state.model_dump_json(indent=2))

    def cancel(self, trigger_id: str) -> bool:
        """Remove a trigger entirely. Returns False if it did not exist."""
        d = self._dir(trigger_id)
        if not d.is_dir():
            return False
        shutil.rmtree(d)
        return True

    # ---- rendering ---------------------------------------------------------- #
    @staticmethod
    def _render_md(spec: TriggerSpec) -> str:
        srcs = "\n".join(
            f"  - {s.kind}: {s.name or s.url} → ctx[{s.ctx_key()!r}]" for s in spec.sources
        ) or "  - (none)"
        return (
            f"# trigger: {spec.id}\n\n"
            f"- **cadence**: {spec.cadence}\n"
            f"- **expires**: {spec.expires.isoformat()}\n"
            f"- **wake symbol**: {spec.wake_symbol()}\n"
            f"- **entry-inducing**: {spec.entry_inducing}\n\n"
            f"## thesis\n\n{spec.thesis}\n\n"
            f"## data sources (ctx)\n\n{srcs}\n\n"
            f"> Rendered from spec.json — do not edit by hand; use the triggers MCP tools.\n"
        )
